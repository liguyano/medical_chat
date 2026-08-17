"""Celery任务定义
作用：定义三个智能体的后台任务，以及定时清理、测试任务。
说明：所有任务均注册到 celery_config 中的全局唯一 celery_app 实例。
"""
import logging

from app.celery_app.celery_config import celery_app

logger = logging.getLogger(__name__)


# ==================== Schedule Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.schedule_agent_worker", bind=True)
def schedule_agent_worker(self, session_id: str, task_config: dict):
    """Schedule Agent后台任务
    作用：调度智能体，监控对话进度，检测偏离，注入约束
    Args:
        - session_id: 会话ID
        - task_config: 任务配置（包含量表ID列表等）
            必需字段：
            - scale_codes: List[str] - 量表编码列表
            可选字段：
            - check_interval: int - 检查间隔（默认5轮）
    """
    import asyncio
    from app.managers.assessment_loader import AssessmentQuestionLoader
    from medagent.agents.service_agent.schedule_agent import ScheduleAgent
    from app.utils.redis_client import get_redis
    from app.managers.dialog_history_manager import DialogHistoryManager
    from app.workers.event_publisher import DialogEventPublisher
    from app.schemas.events import ConstraintEvent, SessionEndEvent, EventType
    from openai import AsyncOpenAI
    from app.configs.app_config import get_app_config

    async def _run_schedule_agent():
        """异步执行Schedule Agent逻辑"""
        try:
            logger.info(f"[Schedule Agent] 启动任务: session_id={session_id}")

            # 1. 加载量表问题列表
            scale_codes = task_config.get("scale_codes", [])
            if not scale_codes:
                logger.error(f"[Schedule Agent] 缺少量表编码列表: {task_config}")
                return {"status": "failed", "reason": "missing_scale_codes"}

            loader = AssessmentQuestionLoader()
            questions = await loader.load_questions_by_scale_codes(scale_codes)

            if not questions:
                logger.warning(f"[Schedule Agent] 未加载到问题: scale_codes={scale_codes}")
                return {"status": "failed", "reason": "no_questions_loaded"}

            logger.info(f"[Schedule Agent] 加载问题: {len(questions)}题")

            # 2. 初始化 LLM 客户端（OpenAI 兼容接口）
            cfg = get_app_config()
            llm_config = cfg.get_llm_config("schedule_agent")  # 从config.yaml读取
            if not llm_config:
                logger.error("[Schedule Agent] 未配置 schedule_agent LLM")
                return {"status": "failed", "reason": "llm_not_configured"}

            llm_client = AsyncOpenAI(
                api_key=llm_config.get("api_key"),
                base_url=llm_config.get("api_base"),
                timeout=llm_config.get("timeout", 30.0),
                max_retries=llm_config.get("max_retries", 2),
            )
            llm_client.model = llm_config.get("model")

            # 3. 实例化 Schedule Agent
            check_interval = task_config.get("check_interval", 5)
            agent = ScheduleAgent(
                session_id=session_id,
                task_list=questions,
                llm_client=llm_client,
                check_interval=check_interval,
            )

            # 4. 订阅 dialog_stream
            redis_client = get_redis()
            stream_key = f"dialog_stream:{session_id}"
            last_id = "0"

            # 从Redis读取轮次计数器（支持任务重启恢复）
            counter_key = f"schedule_agent:turn_counter:{session_id}"
            saved_counter = redis_client.get(counter_key)
            if saved_counter:
                agent.turn_counter = int(saved_counter)
                logger.info(f"[Schedule Agent] 恢复轮次计数器: {agent.turn_counter}")

            logger.info(f"[Schedule Agent] 开始订阅: {stream_key}")

            # 5. 进入消息循环
            timeout_count = 0
            max_timeout = 12  # 最多12次超时（即60秒无消息）后退出

            while True:
                # 读取新消息（阻塞5秒）
                messages = redis_client.xread({stream_key: last_id}, count=1, block=5000)

                if not messages:
                    timeout_count += 1
                    if timeout_count >= max_timeout:
                        logger.info(
                            f"[Schedule Agent] 长时间无消息，任务退出: session={session_id}"
                        )
                        break
                    continue

                timeout_count = 0  # 重置超时计数

                for stream, msg_list in messages:
                    for message_id, data in msg_list:
                        last_id = message_id

                        # 只处理 dialog_turn 事件
                        event_type = data.get("event_type")
                        if event_type != EventType.DIALOG_TURN.value:
                            continue

                        logger.info(f"[Schedule Agent] 收到对话轮次事件: turn={data.get('turn_number')}")

                        # 6. 获取对话历史
                        history_manager = DialogHistoryManager()
                        history = await history_manager.get_dialog_history(
                            session_id, limit=30
                        )
                        lc_history = history_manager.format_for_langchain(history)

                        # 7. 执行检查
                        result = await agent.evaluate(lc_history)

                        # 保存轮次计数器到Redis
                        redis_client.setex(counter_key, 3600, agent.turn_counter)

                        # 8. 如果偏离或遗漏工具，发布约束事件
                        if result.is_deviation:
                            publisher = DialogEventPublisher(session_id)
                            constraint_event = ConstraintEvent(
                                session_id=session_id,
                                constraint_type="deviation",
                                constraint_prompt=result.constraint_prompt,
                                remaining_tasks=result.remaining_questions,
                            )
                            publisher.publish(constraint_event)
                            logger.warning(
                                f"[Schedule Agent] 发布约束事件: {result.constraint_prompt}"
                            )

                        # 9. 检查是否所有问题完成
                        if not result.remaining_questions:
                            logger.info(
                                f"[Schedule Agent] 所有问题已完成: {session_id}"
                            )
                            # 发布会话结束事件
                            publisher = DialogEventPublisher(session_id)
                            end_event = SessionEndEvent(
                                session_id=session_id,
                                end_reason="completed",
                                total_turns=agent.turn_counter,
                                duration_seconds=0,  # TODO: 计算实际时长
                            )
                            publisher.publish(end_event)
                            break

            logger.info(f"[Schedule Agent] 任务完成: session_id={session_id}")
            return {"status": "completed", "session_id": session_id}

        except Exception as e:
            logger.exception(f"[Schedule Agent] 任务执行异常: {e}")
            raise

    try:
        # 运行异步任务
        result = asyncio.run(_run_schedule_agent())
        return result

    except Exception as e:
        logger.error(f"[Schedule Agent] 任务失败: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)


# ==================== Dialog Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.dialog_agent_preheat", bind=True)
def dialog_agent_preheat(self, session_id: str, patient_info: dict):
    """Dialog Agent预热任务
    作用：创建WebSocket连接，初始化豆包语音会话
    Args:
        - session_id: 会话ID
        - patient_info: 患者信息（用于个性化提示词）
    """
    try:
        logger.info(f"[Dialog Agent] 预热任务启动: session_id={session_id}")

        # TODO: 实现Dialog Agent预热逻辑
        # 1. 创建DoubaoVoiceEngine实例
        # 2. 建立WebSocket连接
        # 3. 初始化系统提示词
        # 4. 注册工具列表（宣教、知情同意书）
        # 5. 保存智能体状态到Redis

        logger.info(f"[Dialog Agent] 预热完成: session_id={session_id}")
        return {"status": "preheated", "session_id": session_id}

    except Exception as e:
        logger.error(f"[Dialog Agent] 预热失败: {e}")
        raise self.retry(exc=e, countdown=5, max_retries=3)


# ==================== Field Extraction Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.extraction_agent_worker", bind=True)
def extraction_agent_worker(self, session_id: str, form_ids: list):
    """Field Extraction Agent后台任务
    作用：从对话历史中抽取结构化字段
    Args:
        - session_id: 会话ID
        - form_ids: 量表ID列表
    """
    try:
        logger.info(f"[Extraction Agent] 启动任务: session_id={session_id}")

        # TODO: 实现Field Extraction Agent逻辑
        # 1. 订阅dialog_stream事件
        # 2. 批量读取对话历史
        # 3. 调用大模型抽取字段
        # 4. 计算置信度
        # 5. 保存为 assessment_submission + assessment_answer
        # 6. 发布进度更新事件

        logger.info(f"[Extraction Agent] 任务完成: session_id={session_id}")
        return {"status": "completed", "session_id": session_id}

    except Exception as e:
        logger.error(f"[Extraction Agent] 任务失败: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)


# ==================== 定时任务 ====================

@celery_app.task(name="app.celery_app.tasks.cleanup_expired_sessions")
def cleanup_expired_sessions():
    """清理过期会话
    作用：定期清理超时未活跃的会话
    """
    try:
        logger.info("[定时任务] 清理过期会话")

        # TODO: 实现清理逻辑
        # 1. 查询超过5分钟无活跃的会话（last_active_at）
        # 2. 标记为paused状态
        # 3. 推送护士通知
        # 4. 清理Redis中的智能体状态

        return {"status": "completed"}

    except Exception as e:
        logger.error(f"[定时任务] 清理失败: {e}")
        raise


# ==================== 测试任务 ====================

@celery_app.task(name="app.celery_app.tasks.test_task")
def test_task(x: int, y: int):
    """测试任务
    作用：验证Celery配置是否正常
    """
    logger.info(f"[测试任务] 执行: {x} + {y}")
    result = x + y
    logger.info(f"[测试任务] 结果: {result}")
    return result
