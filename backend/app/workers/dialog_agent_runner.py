"""Dialog Agent Runner：AI 主导问诊执行器
作用：消费患者答案事件，驱动 DialogAgent.handle_patient_input 产出下一个问诊问题。
说明：
  - AI 扮演医护人员主导问诊：AI 先问（从 Task-todo 首题开始），患者答，AI 根据答案+约束产出下一问；
  - 开场白 = AI 的第一个问诊问题，发生在任何患者输入之前；
  - 循环消费 patient_answer 事件（患者答案），每轮调用 handle_patient_input 产出下一问并发 dialog_message；
  - 会话状态（turn_counter/Task-todo 指针/last_event_id）存 Redis `dialog_agent:state:{session_id}`；
  - 每轮从 DB 历史重建 TextChatEngine（无需持久化引擎内存态）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.managers.agent_state_manager import AsyncAgentStateManager
from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.schemas.events import DialogMessageEvent, EventType
from app.utils.redis_client import RedisClient
from app.workers.event_publisher import DialogEventPublisher
from medagent.agents.factory import create_dialog_agent
from medagent.agents.service_agent.schedule_agent.models import QuestionTask

logger = logging.getLogger(__name__)


def _decode(value: Any) -> Any:
    """将 Redis bytes 转换为 UTF-8 文本"""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def decode_stream_fields(
    fields: dict[bytes, bytes], json_fields: set[str] | None = None
) -> dict[str, Any]:
    """解码 Redis Stream FLAT 字段（复用 schedule runner 逻辑）
    Args:
        - fields: Redis xread 返回的原始字段字典
        - json_fields: 需要 json.loads 的字段名集合
    Return:
        - 解码后的字符串键字典
    """
    json_fields = json_fields or set()
    decoded = {}
    for key, value in fields.items():
        key_str = _decode(key)
        value_str = _decode(value)
        decoded[key_str] = (
            json.loads(value_str) if key_str in json_fields else value_str
        )
    return decoded


class DialogAgentRunner:
    """Dialog Agent 主导问诊执行器
    作用：AI 主导问诊循环 —— 首轮发开场白，后续轮消费患者答案产出下一问。
    类参数：
        - session_id: 会话 ID
        - patient_info: 患者信息字典
        - scale_codes: 量表编码列表
        - model: LangChain BaseChatModel（应用层注入）
        - redis_client: Redis 客户端
        - state_ttl: 状态 TTL（秒）
    """

    def __init__(
        self,
        *,
        session_id: str,
        patient_info: dict[str, Any],
        scale_codes: list[str],
        model: BaseChatModel,
        redis_client: RedisClient,
        state_ttl: int = 3600,
    ) -> None:
        self.session_id = session_id
        self.patient_info = patient_info
        self.scale_codes = scale_codes
        self.model = model
        self.redis = redis_client
        self.state_ttl = state_ttl

        self.stream_key = f"dialog_stream:{session_id}"
        self.state_key = f"dialog_agent:state:{session_id}"
        self.loader = AssessmentQuestionLoader()
        self.history_manager = DialogHistoryManager()
        self.publisher = DialogEventPublisher(session_id, redis_client)

    async def run(self, check_interval: int = 5) -> dict[str, Any]:
        """执行 AI 主导问诊循环
        作用：
          1. 首轮：取 Task-todo 首题 → 产出开场提问 → 发 dialog_message
          2. 后续轮：xread patient_answer → handle_patient_input → 发 dialog_message
          3. Task-todo 问完且无约束追加 → 发 session_end
        Args:
            - check_interval: 阻塞读超时（秒）
        Return:
            - 执行结果字典 {status, session_id, total_turns}
        """
        # 1. 加载 Task-todo（量表问题列表）
        questions = await self.loader.load_questions_by_scale_codes(self.scale_codes)
        if not questions:
            logger.error(
                f"[Dialog Runner] 未加载到问题: scale_codes={self.scale_codes}"
            )
            return {"status": "failed", "reason": "no_questions_loaded"}

        logger.info(
            f"[Dialog Runner] 加载 Task-todo: {len(questions)} 项, session={self.session_id}"
        )

        # 2. 创建 DialogAgent（文本引擎，依赖注入）
        from app.workers.dialog_agent_runtime import get_runtime_dependencies

        deps = get_runtime_dependencies(self.session_id)
        agent = create_dialog_agent(
            session_id=self.session_id,
            patient_info=self.patient_info,
            task_list=questions,
            engine_type="text",
            agent_name="dialog_agent",
            middlewares=deps["middlewares"],
            state_store=deps["state_store"],
            history_store=deps["history_store"],
            tool_executor=deps["tool_executor"],
        )

        # 初始化 agent（构建 system prompt + 保存初始状态）
        await agent.initialize()
        logger.info(f"[Dialog Runner] Agent 初始化完成: session={self.session_id}")

        # 3. 恢复或初始化状态
        state = self._restore_state() or {
            "turn_counter": 0,
            "task_todo_pointer": 0,
            "last_event_id": "0",
        }
        turn_counter = state["turn_counter"]
        task_todo_pointer = state["task_todo_pointer"]
        last_event_id = state["last_event_id"]

        # 4. 首轮：发开场白（第一个问诊问题）
        if turn_counter == 0 and task_todo_pointer < len(questions):
            first_question_text = questions[task_todo_pointer].patient_text or questions[
                task_todo_pointer
            ].question_name
            logger.info(
                f"[Dialog Runner] 发送开场白: session={self.session_id}, "
                f"question={first_question_text[:30]}"
            )

            # 发 dialog_message 事件（AI 提问，患者/监控端 SSE 消费）
            opening_event = DialogMessageEvent(
                event_type=EventType.DIALOG_MESSAGE.value,
                session_id=self.session_id,
                turn_number=1,
                role="assistant",
                content=first_question_text,
                question_id=questions[task_todo_pointer].question_id,
            )
            self.publisher.publish(opening_event)

            turn_counter += 1
            task_todo_pointer += 1
            self._save_state(
                {"turn_counter": turn_counter, "task_todo_pointer": task_todo_pointer, "last_event_id": last_event_id}
            )

        # 5. 主循环：消费 patient_answer 事件 → handle_patient_input → 发下一问
        max_idle_reads = 60  # 连续 60 次无消息则退出（5s * 60 = 5min）
        idle_count = 0

        logger.info(f"[Dialog Runner] 进入主循环: session={self.session_id}")

        while True:
            try:
                # xread 阻塞读 patient_answer 事件
                messages = self.redis.xread(
                    {self.stream_key: last_event_id},
                    count=1,
                    block=check_interval * 1000,
                )

                if not messages:
                    idle_count += 1
                    if idle_count >= max_idle_reads:
                        logger.info(
                            f"[Dialog Runner] 超时无患者答案，退出: session={self.session_id}"
                        )
                        return {
                            "status": "timeout",
                            "session_id": self.session_id,
                            "total_turns": turn_counter,
                        }
                    continue

                idle_count = 0

                # 解析事件
                for _stream, entries in messages:
                    for raw_id, raw_fields in entries:
                        last_event_id = _decode(raw_id)
                        fields = decode_stream_fields(raw_fields, json_fields={"metadata"})
                        event_type = fields.get("event_type")

                        # 只处理 patient_answer 事件
                        if event_type != EventType.PATIENT_ANSWER.value:
                            continue

                        patient_text = fields.get("content", "")
                        logger.info(
                            f"[Dialog Runner] 收到患者答案: turn={turn_counter}, "
                            f"answer={patient_text[:30]}"
                        )

                        # 调用 DialogAgent.handle_patient_input 产出下一问
                        # （中间件 before: 关键词/约束注入 → 模型推理 → 中间件 after: 发给 extraction/schedule）
                        next_question = await agent.handle_patient_input(
                            patient_text, session_no=self.session_id
                        )

                        turn_counter += 1

                        # 发 dialog_message（AI 提问）
                        next_question_id = (
                            questions[task_todo_pointer].question_id
                            if task_todo_pointer < len(questions)
                            else None
                        )
                        next_event = DialogMessageEvent(
                            event_type=EventType.DIALOG_MESSAGE.value,
                            session_id=self.session_id,
                            turn_number=turn_counter,
                            role="assistant",
                            content=next_question,
                            question_id=next_question_id,
                        )
                        self.publisher.publish(next_event)

                        # 更新 Task-todo 指针（简化：每次+1，实际应根据 Schedule 约束动态跳转）
                        if task_todo_pointer < len(questions):
                            task_todo_pointer += 1

                        # 保存状态
                        self._save_state(
                            {
                                "turn_counter": turn_counter,
                                "task_todo_pointer": task_todo_pointer,
                                "last_event_id": last_event_id,
                            }
                        )

                        # 检查完成条件：Task-todo 问完且无约束追加
                        if task_todo_pointer >= len(questions):
                            # TODO: 查询 Schedule Agent 是否还有未处理约束
                            logger.info(
                                f"[Dialog Runner] Task-todo 完成: session={self.session_id}, "
                                f"total_turns={turn_counter}"
                            )
                            # 发 session_end 事件（TODO: 定义 SessionEndEvent）
                            return {
                                "status": "completed",
                                "session_id": self.session_id,
                                "total_turns": turn_counter,
                            }

            except KeyboardInterrupt:
                logger.info(f"[Dialog Runner] 收到中断信号: session={self.session_id}")
                break
            except Exception:
                logger.exception(f"[Dialog Runner] 处理失败: session={self.session_id}")
                await asyncio.sleep(5)

        return {
            "status": "interrupted",
            "session_id": self.session_id,
            "total_turns": turn_counter,
        }

    def _restore_state(self) -> dict[str, Any] | None:
        """从 Redis 恢复状态"""
        raw = self.redis.get(self.state_key)
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            logger.exception(f"[Dialog Runner] 状态恢复失败: {self.state_key}")
            return None

    def _save_state(self, state: dict[str, Any]) -> None:
        """保存状态到 Redis"""
        try:
            self.redis.set(self.state_key, json.dumps(state), ex=self.state_ttl)
        except Exception:
            logger.exception(f"[Dialog Runner] 状态保存失败: {self.state_key}")
            raise RuntimeError(f"Dialog Agent 状态保存失败: {self.state_key}")
