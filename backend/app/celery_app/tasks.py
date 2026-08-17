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
    """Schedule Agent 后台任务
    作用：组装 OpenAI 兼容客户端并运行可恢复的 Redis Stream 调度循环。
    """
    import asyncio

    from medagent.providers import create_chat_model

    from app.celery_app.runtime import ensure_worker_runtime
    from app.configs.app_config import get_app_config
    from app.managers.assessment_loader import AssessmentQuestionLoader
    from app.managers.dialog_history_manager import DialogHistoryManager
    from app.utils.redis_client import get_redis
    from app.workers.event_publisher import DialogEventPublisher
    from app.workers.schedule_agent_runner import ScheduleAgentRunner

    try:
        config = get_app_config()
        model_config = config.get_agent_model_config("schedule_agent")
        if model_config is None:
            return {"status": "failed", "reason": "llm_not_configured"}

        ensure_worker_runtime()
        model = create_chat_model(model_config)
        runner = ScheduleAgentRunner(
            loader=AssessmentQuestionLoader(),
            history_manager=DialogHistoryManager(),
            redis_client=get_redis(),
            publisher_factory=DialogEventPublisher,
            model=model,
        )
        return asyncio.run(
            runner.run(
                session_id,
                scale_codes=task_config.get("scale_codes", []),
                check_interval=task_config.get("check_interval", 5),
            )
        )
    except Exception as exc:
        logger.exception("[Schedule Agent] Celery任务失败: session=%s", session_id)
        raise self.retry(exc=exc, countdown=10, max_retries=3)


# ==================== Dialog Agent任务 ====================


@celery_app.task(name="app.celery_app.tasks.dialog_agent_worker", bind=True)
def dialog_agent_worker(self, session_id: str, patient_info: dict, task_config: dict):
    """Dialog Agent 后台任务
    作用：运行 AI 主导问诊循环，首轮发开场白，后续轮消费患者答案产出下一问
    Args:
        - session_id: 会话ID
        - patient_info: 患者信息
        - task_config: 任务配置
            必需字段：
            - scale_codes: List[str] - 量表编码列表
            可选字段：
            - check_interval: int - Redis Stream 阻塞读取间隔（秒，默认 5）
    """
    import asyncio

    from medagent.providers import create_chat_model

    from app.celery_app.runtime import ensure_worker_runtime
    from app.configs.app_config import get_app_config
    from app.utils.redis_client import get_redis
    from app.workers.dialog_agent_runner import DialogAgentRunner

    try:
        config = get_app_config()
        model_config = config.get_agent_model_config("dialog_agent")
        if model_config is None:
            return {"status": "failed", "reason": "llm_not_configured"}

        ensure_worker_runtime()
        model = create_chat_model(model_config)

        runner = DialogAgentRunner(
            session_id=session_id,
            patient_info=patient_info,
            scale_codes=task_config.get("scale_codes", []),
            model=model,
            redis_client=get_redis(),
        )

        return asyncio.run(runner.run(check_interval=task_config.get("check_interval", 5)))
    except Exception as exc:
        logger.exception("[Dialog Agent] Celery任务失败: session=%s", session_id)
        raise self.retry(exc=exc, countdown=10, max_retries=3)


@celery_app.task(name="app.celery_app.tasks.dialog_agent_preheat", bind=True)
def dialog_agent_preheat(self, session_id: str, patient_info: dict, task_config: dict):
    """Dialog Agent预热任务
    作用：校验文本模型与量表配置，并保存可恢复的预热标记
    Args:
        - session_id: 会话ID
        - patient_info: 患者信息（用于个性化提示词）
        - task_config: 任务配置
            必需字段：
            - scale_codes: List[str] - 量表编码列表
            可选字段：
            - engine_type: str - 引擎类型（'text' | 'doubao'，默认 'text'）
    """
    import asyncio

    from app.celery_app.runtime import ensure_worker_runtime
    from app.managers.assessment_loader import AssessmentQuestionLoader
    from app.utils.redis_client import get_redis

    async def _run_preheat():
        """异步执行预热逻辑"""
        try:
            logger.info(f"[Dialog Agent] 预热任务启动: session_id={session_id}")

            # 1. 加载量表问题列表
            scale_codes = task_config.get("scale_codes", [])
            if not scale_codes:
                logger.error(f"[Dialog Agent] 缺少量表编码列表: {task_config}")
                return {"status": "failed", "reason": "missing_scale_codes"}

            ensure_worker_runtime()
            loader = AssessmentQuestionLoader()
            questions = await loader.load_questions_by_scale_codes(scale_codes)
            if not questions:
                logger.error(f"[Dialog Agent] 未加载到问题: scale_codes={scale_codes}")
                return {"status": "failed", "reason": "no_questions_loaded"}

            logger.info(f"[Dialog Agent] 加载量表问题: {len(questions)} 项")

            # 2. 第一期仅允许文本引擎
            engine_type = task_config.get("engine_type", "text")
            if engine_type != "text":
                logger.error(f"[Dialog Agent] 未知引擎类型: {engine_type}")
                return {"status": "failed", "reason": "unknown_engine_type"}
            redis = get_redis()
            saved = redis.set(
                f"dialog_agent:preheated:{session_id}",
                {
                    "engine_type": engine_type,
                    "scale_codes": scale_codes,
                    "question_count": len(questions),
                    "patient_info": patient_info,
                },
                ex=3600,
            )
            if not saved:
                raise RuntimeError("Dialog Agent预热标记保存失败")

            return {
                "status": "preheated",
                "session_id": session_id,
                "engine_type": engine_type,
                "question_count": len(questions),
            }

        except Exception:
            logger.exception("[Dialog Agent] 预热失败")
            raise

    try:
        # 运行异步任务
        result = asyncio.run(_run_preheat())
        logger.info(f"[Dialog Agent] 预热完成: {result}")
        return result

    except Exception as e:  # noqa: BLE001
        logger.error(f"[Dialog Agent] 预热任务失败: {e}")
        raise self.retry(exc=e, countdown=5, max_retries=3)


# ==================== Field Extraction Agent任务 ====================


@celery_app.task(name="app.celery_app.tasks.extraction_agent_worker", bind=True)
def extraction_agent_worker(self, session_id: str, task_config: dict):
    """Field Extraction Agent 后台任务
    作用：订阅对话流，调用抽取 Agent，写入数据库，发布结果
    Args:
        - session_id: 会话ID
        - task_config: 任务配置
            必需字段：
            - scale_codes: List[str] - 量表编码列表
            可选字段：
            - check_interval: int - Redis Stream 阻塞读取间隔（秒，默认 5）
    """
    import asyncio

    from medagent.providers import create_chat_model

    from app.celery_app.runtime import ensure_worker_runtime
    from app.configs.app_config import get_app_config
    from app.managers.assessment_loader import AssessmentQuestionLoader
    from app.managers.dialog_history_manager import DialogHistoryManager
    from app.managers.extraction_result_writer import ExtractionResultWriter
    from app.utils.redis_client import get_redis
    from app.workers.event_publisher import DialogEventPublisher
    from app.workers.extraction_agent_runner import ExtractionAgentRunner

    try:
        config = get_app_config()
        model_config = config.get_agent_model_config("extraction_agent")
        if model_config is None:
            return {"status": "failed", "reason": "llm_not_configured"}

        ensure_worker_runtime()
        model = create_chat_model(model_config)

        runner = ExtractionAgentRunner(
            loader=AssessmentQuestionLoader(),
            history_manager=DialogHistoryManager(),
            writer_factory=ExtractionResultWriter,
            redis_client=get_redis(),
            publisher_factory=DialogEventPublisher,
            model=model,
        )

        return asyncio.run(
            runner.run(
                session_id,
                scale_codes=task_config.get("scale_codes", []),
                check_interval=task_config.get("check_interval", 5),
            )
        )
    except Exception as exc:
        logger.exception("[Extraction Agent] Celery任务失败: session=%s", session_id)
        raise self.retry(exc=exc, countdown=10, max_retries=3)


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
