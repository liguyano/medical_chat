"""Extraction Agent Runner - Celery 任务编排
作用：订阅 Redis Stream，调用 Field Extraction Agent，写入数据库，发布事件
"""

import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI
from redis import Redis

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.managers.extraction_result_writer import ExtractionResultWriter
from app.workers.event_publisher import DialogEventPublisher
from medagent.agents.service_agent.extraction_agent import FieldExtractionAgent

logger = logging.getLogger(__name__)


class ExtractionAgentRunner:
    """Field Extraction Agent 编排器
    作用：类比 ScheduleAgentRunner，负责订阅事件、调用 Agent、写库、发布结果
    """

    def __init__(
        self,
        loader: AssessmentQuestionLoader,
        history_manager: DialogHistoryManager,
        writer_factory: type[ExtractionResultWriter],
        redis_client: Redis,
        publisher_factory: type[DialogEventPublisher],
        llm_client: AsyncOpenAI,
        model_config: dict[str, Any],
    ):
        """初始化 Runner
        Args:
            - loader: 量表问题加载器
            - history_manager: 对话历史管理器
            - writer_factory: 字段写入器工厂
            - redis_client: Redis 客户端
            - publisher_factory: 事件发布器工厂
            - llm_client: AsyncOpenAI 客户端
            - model_config: 模型配置
        """
        self.loader = loader
        self.history_manager = history_manager
        self.writer_factory = writer_factory
        self.redis_client = redis_client
        self.publisher_factory = publisher_factory
        self.llm_client = llm_client
        self.model_config = model_config

    async def run(
        self,
        session_id: str,
        scale_codes: list[str],
        check_interval: int = 5,
    ) -> dict:
        """主循环：订阅对话事件 → 抽取字段 → 写库 → 发布结果
        Args:
            - session_id: 会话ID
            - scale_codes: 量表编码列表
            - check_interval: Redis Stream 阻塞读取间隔（秒）
        Return:
            - {"status": "completed" | "failed", "total_extracted": 10, ...}
        """
        stream_key = f"dialog_stream:{session_id}"
        consumer_group = "extraction_agent_group"
        consumer_name = f"extraction_worker_{session_id}"

        # 确保 consumer group 存在
        try:
            self.redis_client.xgroup_create(
                stream_key, consumer_group, id="0", mkstream=True
            )
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.warning(f"[Extraction Runner] 创建 consumer group 失败: {e}")

        # 加载量表问题
        questions = await self.loader.load_questions_by_scale_codes(scale_codes)
        if not questions:
            logger.error(
                f"[Extraction Runner] 未加载到问题: scale_codes={scale_codes}"
            )
            return {"status": "failed", "reason": "no_questions_loaded"}

        # 构建 scale_version 信息（简化处理）
        scale_version = {
            "scale_name": "入院评估量表",  # TODO: 从数据库读取
            "version_code": "v1.0",
        }

        # 创建 Agent
        agent = FieldExtractionAgent(
            session_id=session_id,
            scale_codes=scale_codes,
            llm_client=self.llm_client,
            model_config=self.model_config,
        )

        writer = self.writer_factory()
        publisher = self.publisher_factory(redis_client=self.redis_client)

        # 摘要缓存键
        summary_cache_key = f"dialog_summary:{session_id}"

        # 获取提交记录ID（假设已由 API 创建 assessment_instance）
        # TODO: 从数据库查询 assessment_instance_id 和 interaction_session_id
        assessment_instance_id = 1  # 占位
        interaction_session_id = 1  # 占位

        submission_id = None
        total_extracted = 0

        logger.info(
            f"[Extraction Runner] 启动监听: session={session_id}, stream={stream_key}"
        )

        while True:
            try:
                # 读取 Redis Stream（阻塞）
                messages = self.redis_client.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {stream_key: ">"},
                    count=1,
                    block=check_interval * 1000,
                )

                if not messages:
                    # 超时无新消息，继续等待
                    continue

                # 解析事件
                for stream, msg_list in messages:
                    for msg_id, msg_data in msg_list:
                        event = json.loads(msg_data[b"data"].decode("utf-8"))

                        if event.get("event_type") != "dialog_turn":
                            # 忽略非对话轮次事件
                            continue

                        logger.info(
                            f"[Extraction Runner] 收到对话事件: turn={event.get('turn_number')}"
                        )

                        # 1. 读取历史抽取字段
                        previous_extraction = {}
                        if submission_id:
                            previous_extraction = (
                                await writer.get_previous_extraction(submission_id)
                            )

                        # 2. 生成对话摘要（优先从缓存读取）
                        history_summary = self.redis_client.get(summary_cache_key)
                        if history_summary:
                            history_summary = history_summary.decode("utf-8")
                        else:
                            history_summary = await self.history_manager.summarize_history(
                                session_id, self.llm_client, max_turns=20
                            )
                            # 缓存 1 小时
                            self.redis_client.setex(
                                summary_cache_key, 3600, history_summary
                            )

                        # 3. 获取新对话
                        new_dialog = [
                            {
                                "turn": event.get("turn_number"),
                                "patient": event.get("question", ""),
                                "ai": event.get("answer", ""),
                            }
                        ]

                        # 4. 调用 Agent 抽取字段（带重试）
                        extraction_result = await agent.extract_with_retry(
                            previous_extraction=previous_extraction,
                            history_summary=history_summary,
                            new_dialog=new_dialog,
                            scale_version=scale_version,
                            questions=questions,
                            max_retries=3,
                        )

                        if extraction_result is None:
                            # 抽取失败，标记人工补录
                            logger.error(
                                f"[Extraction Runner] 抽取失败，需人工补录: session={session_id}"
                            )
                            # TODO: 更新 care_task.need_manual_intervention=True
                            break

                        # 5. 写入数据库
                        submission = await writer.upsert_submission(
                            interaction_session_id=interaction_session_id,
                            assessment_instance_id=assessment_instance_id,
                            extraction_result=extraction_result,
                        )
                        submission_id = submission.id

                        await writer.upsert_answers(
                            submission_id=submission_id,
                            extracted_answers=extraction_result.extracted_answers,
                        )

                        # TODO: upsert_answer_options（单选/多选题）

                        await writer.calculate_scores(
                            submission_id=submission_id,
                            scale_version_id=1,  # 占位
                        )

                        total_extracted = submission.answered_question_count

                        # 6. 更新摘要缓存（追加当前轮）
                        # 简化处理：每 5 轮重新生成摘要
                        if event.get("turn_number", 0) % 5 == 0:
                            self.redis_client.delete(summary_cache_key)

                        # 7. 发布 ExtractionResultEvent
                        await publisher.publish_extraction_result(
                            session_id=session_id,
                            extracted_fields={
                                str(ans.question_id): ans.answer_value
                                for ans in extraction_result.extracted_answers
                            },
                            confidence_scores={
                                str(ans.question_id): ans.extraction_confidence
                                for ans in extraction_result.extracted_answers
                            },
                        )

                        # 8. 检查完成度
                        if submission.submission_status == "completed":
                            logger.info(
                                f"[Extraction Runner] 抽取完成: session={session_id}, "
                                f"total={total_extracted}"
                            )
                            # TODO: 发布 ExtractionCompleteEvent
                            return {
                                "status": "completed",
                                "session_id": session_id,
                                "total_extracted": total_extracted,
                            }

                        # ACK 消息
                        self.redis_client.xack(stream_key, consumer_group, msg_id)

            except KeyboardInterrupt:
                logger.info("[Extraction Runner] 收到中断信号，退出")
                break
            except Exception as e:
                logger.exception(f"[Extraction Runner] 处理失败: {e}")
                await asyncio.sleep(5)

        return {
            "status": "interrupted",
            "session_id": session_id,
            "total_extracted": total_extracted,
        }
