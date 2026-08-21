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
    作用：按需创建 Schedule Agent，处理一条患者答案后立即释放实例。
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
        result = asyncio.run(
            runner.run(
                session_id,
                scale_codes=task_config.get("scale_codes", []),
                source_message_id=task_config.get("source_message_id"),
                source_event_id=task_config.get("source_event_id"),
                check_interval=task_config.get("check_interval", 1),
                patient_info=task_config.get("patient_info", {}),
            )
        )
        if result.get("status") == "already_running":
            raise self.retry(countdown=2, max_retries=10)
        return result
    except Exception as exc:
        logger.exception("[Schedule Agent] Celery任务失败: session=%s", session_id)
        raise self.retry(exc=exc, countdown=10, max_retries=3)


# ==================== Dialog Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.dialog_agent_worker", bind=True)
def dialog_agent_worker(self, session_id: str, patient_info: dict, task_config: dict):
    """Dialog Agent 后台任务
    作用：按需创建 Dialog Agent，生成首问或处理一条患者答案后立即释放实例。
    Args:
        - session_id: 会话ID
        - patient_info: 患者信息
        - task_config: 任务配置
            必需字段：
            - scale_codes: List[str] - 量表编码列表
            可选字段：
            - source_message_id: str - 患者答案消息编号；为空时生成首问
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

        # 构造 DialogAgentRunner 实例
        runner = DialogAgentRunner(
            session_id=session_id,
            patient_info=patient_info,
            scale_codes=task_config.get("scale_codes", []),
            model=model,
            redis_client=get_redis(),
        )

        result = asyncio.run(
            runner.run(
                source_message_id=task_config.get("source_message_id"),
                source_event_id=task_config.get("source_event_id"),
                finalize=bool(task_config.get("finalize")),
            )
        )
        if result.get("status") == "already_running":
            raise self.retry(countdown=2, max_retries=10)
        return result
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
    from app.utils.redis_client import get_redis
    from app.workers.schedule_task_store import ScheduleTaskStore

    async def _run_preheat():
        """异步执行预热逻辑"""
        try:
            logger.info(f"[Dialog Agent] 预热任务启动: session_id={session_id}")

            # 1. 读取 Schedule Agent 已生成的 Task-todo
            scale_codes = task_config.get("scale_codes", [])
            if not scale_codes:
                logger.error(f"[Dialog Agent] 缺少量表编码列表: {task_config}")
                return {"status": "failed", "reason": "missing_scale_codes"}

            ensure_worker_runtime()
            engine_type = task_config.get("engine_type", "text")
            if engine_type != "text":
                logger.error(f"[Dialog Agent] 未知引擎类型: {engine_type}")
                return {"status": "failed", "reason": "unknown_engine_type"}
            redis = get_redis()
            plan = ScheduleTaskStore(redis).get_plan(session_id)
            questions = plan.tasks if plan is not None else []
            if plan is None:
                raise RuntimeError(f"Schedule Task-todo 尚未就绪: {session_id}")
            if not questions:
                return {"status": "failed", "reason": "no_questions_loaded"}

            logger.info(f"[Dialog Agent] 加载量表问题: {len(questions)} 项")

            # 2. 第一期仅允许文本引擎
            saved = redis.set(
                f"dialog_agent:preheated:{session_id}",
                {
                    "engine_type": engine_type,
                    "scale_codes": scale_codes,
                    "question_count": len(questions),
                    "patient_info": patient_info,
                    "opening_guidance": plan.opening_guidance if plan else "",
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
    作用：按需创建 Extraction Agent，处理一条患者答案后立即释放实例。
    Args:
        - session_id: 会话ID
        - task_config: 任务配置
            必需字段：
            - scale_codes: List[str] - 量表编码列表
            可选字段：
            - source_message_id: str - 患者答案消息编号
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

        result = asyncio.run(
            runner.run(
                session_id,
                scale_codes=task_config.get("scale_codes", []),
                source_message_id=task_config.get("source_message_id"),
                source_event_id=task_config.get("source_event_id"),
                check_interval=task_config.get("check_interval", 1),
            )
        )
        if result.get("status") == "already_running":
            raise self.retry(countdown=2, max_retries=10)
        if result.get("assessment_completed") and task_config.get("interaction_mode") == "voice":
            from app.services.voice_completion_service import (
                mark_voice_assessment_completed,
            )

            mark_voice_assessment_completed(
                session_id=session_id,
                task_id=task_config.get("task_id"),
            )
        elif result.get("assessment_completed"):
            completion_config = {
                **task_config,
                "source_message_id": None,
                "source_event_id": None,
                "finalize": True,
            }
            dialog_agent_worker.delay(
                session_id,
                task_config.get("patient_info", {}),
                completion_config,
            )
        return result
    except Exception as exc:
        logger.exception("[Extraction Agent] Celery任务失败: session=%s", session_id)
        if self.request.retries >= 3:
            # 达到 Celery 任务上限后停止当前批次，通知医护人工介入。
            from app.models import base as model_base
            from app.models.patient_task import CareTask
            from app.schemas.events import AgentErrorEvent
            from app.utils.redis_client import get_redis
            from app.workers.event_publisher import DialogEventPublisher

            task_id = task_config.get("task_id")
            if task_id and model_base.SessionLocal is not None:
                with model_base.SessionLocal() as db:
                    task = db.get(CareTask, int(task_id))
                    if task is not None:
                        task.need_manual_intervention = True
                        task.intervention_reason = "字段抽取任务达到重试上限，请医护人工填写"
                        task.updator = "extraction_agent"
                        db.commit()
            if task_config.get("task_id"):
                DialogEventPublisher(session_id, get_redis()).publish(
                    AgentErrorEvent(
                        session_id=session_id,
                        task_id=task_config.get("task_id"),
                        agent_name="extraction_agent",
                        error_code="EXTRACTION_RETRY_EXHAUSTED",
                        message="字段抽取任务达到重试上限，请医护人工填写",
                        retrying=False,
                        manual_intervention=True,
                        intervention_reason="字段抽取任务达到重试上限，请医护人工填写",
                    )
                )
            return {
                "status": "manual_intervention",
                "session_id": session_id,
                "task_id": task_id,
            }
        raise self.retry(exc=exc, countdown=10, max_retries=3)


# ==================== Nursing Plan Agent任务 ====================


@celery_app.task(name="app.celery_app.tasks.nursing_plan_worker", bind=True)
def nursing_plan_worker(self, task_id: int, force: bool = False):
    """异步生成患者画像和护理计划 AI 草案。"""
    import asyncio

    from app.celery_app.runtime import ensure_worker_runtime
    from app.models import base as model_base
    from app.services.nursing_plan_service import generate_nursing_plan

    try:
        ensure_worker_runtime()
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            return asyncio.run(
                generate_nursing_plan(
                    db,
                    task_id,
                    force=force,
                )
            ).model_dump(mode="json")
    except Exception as exc:
        logger.exception("[Nursing Plan] Celery任务失败: task=%s", task_id)
        raise self.retry(exc=exc, countdown=15, max_retries=3)


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


@celery_app.task(name="app.celery_app.tasks.reconcile_pending_dialog_turns")
def reconcile_pending_dialog_turns():
    """补偿未完成的患者答案任务
    作用：Worker 重启、Broker 任务丢失或旧版长驻任务超时后，重新派发未生成下一问的单轮流水线。
    """
    from sqlalchemy import func, select

    from app.celery_app.runtime import ensure_worker_runtime
    from app.models import base as model_base
    from app.models.interaction import InteractionMessage, InteractionSession
    from app.services.agent_dispatch_service import (
        dispatch_answer_workers,
        dispatch_opening_workers,
    )

    ensure_worker_runtime()
    if model_base.SessionLocal is None:
        return {"status": "skipped", "reason": "database_not_initialized"}

    dispatched = 0
    with model_base.SessionLocal() as db:
        sessions = list(
            db.scalars(
                select(InteractionSession).where(
                    InteractionSession.session_status == "active",
                    InteractionSession.deleted == 0,
                )
            ).all()
        )
        for session in sessions:
            latest_ai_turn = db.scalar(
                select(func.max(InteractionMessage.turn_no)).where(
                    InteractionMessage.interaction_session_id == session.id,
                    InteractionMessage.role_type.in_(["AI", "assistant"]),
                    InteractionMessage.deleted == 0,
                )
            )
            latest_patient = db.scalar(
                select(InteractionMessage)
                .where(
                    InteractionMessage.interaction_session_id == session.id,
                    InteractionMessage.role_type.in_(["患者", "家属", "user"]),
                    InteractionMessage.deleted == 0,
                )
                .order_by(
                    InteractionMessage.turn_no.desc(),
                    InteractionMessage.id.desc(),
                )
            )
            try:
                if latest_ai_turn is None:
                    dispatch_opening_workers(db, session)
                    dispatched += 1
                elif (
                    latest_patient is not None
                    and latest_patient.turn_no >= latest_ai_turn
                ):
                    dispatch_answer_workers(
                        db,
                        session,
                        source_message_id=latest_patient.message_no,
                        source_event_id=None,
                    )
                    dispatched += 1
            except Exception:
                logger.exception(
                    "[Dialog Reconcile] 补偿派发失败: session=%s",
                    session.session_no,
                )
    return {"status": "completed", "dispatched": dispatched}


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
