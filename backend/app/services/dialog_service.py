"""对话交互服务
作用：封装交互会话的开启、患者消息落库与关键词拦截、对话历史查询。
      遵循计划约束：本服务仅落库 + 发布事件，AI 回复由 Dialog Agent 异步产出经 SSE 回推。
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.managers.keyword_matcher import MatchResult, get_keyword_matcher
from app.models.interaction import InteractionMessage, InteractionSession
from app.models.patient_task import CareTask
from app.schemas.dialog import (
    DialogHistoryResponse,
    DialogResponse,
    MessageItem,
    SendMessageRequest,
    SendMessageResponse,
    StartDialogRequest,
)
from app.schemas.events import ConstraintEvent, DialogTurnEvent
from app.workers.event_publisher import DialogEventPublisher

logger = logging.getLogger(__name__)

# 会话锁：TTL 秒数，防止同一会话并发处理消息
_DIALOG_LOCK_TTL = 30


def _gen_session_no() -> str:
    """生成会话编号。"""
    return f"SESS-{uuid.uuid4().hex[:12]}"


def _gen_message_no() -> str:
    """生成消息编号。"""
    return f"MSG-{uuid.uuid4().hex[:16]}"


def start_dialog(db: Session, req: StartDialogRequest) -> DialogResponse:
    """开始对话
    作用：校验任务可对话后创建 interaction_session，并触发 Dialog Agent 预热。
    Args:
        - db: 数据库会话
        - req: 开始对话请求
    Return:
        - DialogResponse: 新建会话详情
    """
    # 校验任务存在且为 AI 对话采集模式
    task = db.execute(
        select(CareTask).where(
            CareTask.task_no == req.task_no, CareTask.deleted == 0
        )
    ).scalar_one_or_none()
    if task is None:
        raise AppError(ErrorCode.ERR_DIALOG_004)
    if task.collection_mode != "ai_dialogue":
        raise AppError(ErrorCode.ERR_DIALOG_004, "任务采集模式不是 AI 对话，无法开启对话")

    now = datetime.now(UTC)
    session = InteractionSession(
        session_no=_gen_session_no(),
        task_id=task.id,
        patient_id=task.patient_id,
        encounter_id=task.encounter_id,
        participant_type="patient",
        interaction_type="assessment",
        channel_type=req.channel_type,
        session_status="active",
        started_at=now,
        creator="system",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 触发 Dialog Agent 预热（异步；失败不阻断会话创建）
    _trigger_preheat(session.session_no, task, req)

    logger.info(f"交互会话创建成功: session_no={session.session_no} task_no={req.task_no}")
    return DialogResponse(
        session_no=session.session_no,
        task_no=req.task_no,
        session_status=session.session_status,
        started_at=session.started_at,
    )


def _trigger_preheat(session_no: str, task: CareTask, req: StartDialogRequest) -> None:
    """触发 Dialog Agent 预热任务
    作用：向 Celery 投递 dialog_agent_preheat；投递失败仅记录日志，不阻断主流程。
    Args:
        - session_no: 会话编号（作为 Agent 侧 session_id）
        - task: 关联任务
        - req: 开始对话请求
    """
    try:
        from app.celery_app.tasks import dialog_agent_preheat

        dialog_agent_preheat.delay(
            session_id=session_no,
            patient_info={"patient_id": task.patient_id, "encounter_id": task.encounter_id},
            task_config={
                "scale_codes": req.scale_codes,
                "engine_type": req.engine_type,
            },
        )
        logger.info(f"Dialog Agent 预热任务已投递: session_no={session_no}")
    except Exception as e:
        logger.error(f"投递预热任务失败（不阻断会话创建）: session_no={session_no} -> {e}")


def _load_active_session(db: Session, session_no: str) -> InteractionSession:
    """加载处于活动状态的会话
    Args:
        - db: 数据库会话
        - session_no: 会话编号
    Return:
        - InteractionSession
    """
    session = db.execute(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    ).scalar_one_or_none()
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    if session.session_status != "active":
        raise AppError(ErrorCode.ERR_DIALOG_002)
    return session


def _next_turn_no(db: Session, interaction_session_id: int) -> int:
    """计算下一轮次序号
    Args:
        - db: 数据库会话
        - interaction_session_id: 会话主键
    Return:
        - 下一轮次序号（从 1 开始）
    """
    current = db.scalar(
        select(func.max(InteractionMessage.turn_no)).where(
            InteractionMessage.interaction_session_id == interaction_session_id,
            InteractionMessage.deleted == 0,
        )
    )
    return int(current or 0) + 1


async def send_message(
    db: Session, session_no: str, req: SendMessageRequest
) -> SendMessageResponse:
    """发送患者消息
    作用：加会话锁防并发 -> 落库患者消息 -> 关键词拦截并发约束事件 -> 发布 DialogTurnEvent。
          不同步调用模型；AI 回复由 Dialog Agent 消费事件后异步产出。
    Args:
        - db: 数据库会话
        - session_no: 会话编号
        - req: 发送消息请求
    Return:
        - SendMessageResponse: 落库消息编号、轮次与是否命中拦截
    """
    from app.utils.redis_client import get_async_redis

    session = _load_active_session(db, session_no)

    if not req.content_text and not req.audio_base64:
        raise AppError(ErrorCode.ERR_COMMON_001, "content_text 与 audio_base64 不能同时为空")

    redis = get_async_redis()
    lock_key = f"dialog_lock:{session_no}"
    lock_token = uuid.uuid4().hex

    # 获取会话锁，防止同一会话并发处理消息
    acquired = await redis.acquire_lock(lock_key, lock_token, ttl=_DIALOG_LOCK_TTL)
    if not acquired:
        raise AppError(ErrorCode.ERR_DIALOG_003)

    try:
        turn_no = _next_turn_no(db, session.id)
        message_no = _gen_message_no()

        # 落库患者消息
        message = InteractionMessage(
            interaction_session_id=session.id,
            message_no=message_no,
            turn_no=turn_no,
            role_type="患者",
            message_type=req.message_type,
            content_text=req.content_text,
            audio_url=None,
            occurred_at=datetime.now(UTC),
            creator="patient",
        )
        db.add(message)
        db.commit()

        # 关键词拦截（步骤7）
        matches = get_keyword_matcher().match(req.content_text)
        intercepted = bool(matches)

        publisher = DialogEventPublisher(session_id=session_no)

        # 发布对话轮次事件，交由 Dialog Agent 异步生成回复
        publisher.publish(
            DialogTurnEvent(
                session_id=session_no,
                turn_number=turn_no,
                question=req.content_text or "",
                answer="",
                metadata={"message_no": message_no, "intercepted": intercepted},
            )
        )

        # 命中关键词则追加约束事件，供 Agent 注入下一轮约束提示
        if intercepted:
            _publish_constraint(publisher, session_no, matches)

        logger.info(
            f"患者消息处理完成: session_no={session_no} turn={turn_no} "
            f"intercepted={intercepted} matched={[m.rule_code for m in matches]}"
        )
        return SendMessageResponse(
            session_no=session_no,
            message_no=message_no,
            turn_no=turn_no,
            intercepted=intercepted,
        )
    finally:
        await redis.release_lock(lock_key, lock_token)


def _publish_constraint(
    publisher: DialogEventPublisher,
    session_no: str,
    matches: list[MatchResult],
) -> None:
    """发布关键词命中的约束事件
    作用：将命中规则的约束提示合并后发布 ConstraintEvent。
    Args:
        - publisher: 事件发布器
        - session_no: 会话编号
        - matches: 命中规则列表（已按优先级降序）
    """
    prompts = [m.constraint_prompt for m in matches if m.constraint_prompt]
    if not prompts:
        return
    publisher.publish(
        ConstraintEvent(
            session_id=session_no,
            constraint_type="keyword_hit",
            constraint_prompt="\n".join(prompts),
            remaining_tasks=[],
        )
    )
    logger.info(f"关键词约束事件已发布: session_no={session_no} 命中 {len(matches)} 条规则")


async def get_history(db: Session, session_no: str) -> DialogHistoryResponse:
    """获取对话历史
    Args:
        - db: 数据库会话
        - session_no: 会话编号
    Return:
        - DialogHistoryResponse: 会话历史消息列表
    """
    session = db.execute(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    ).scalar_one_or_none()
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)

    rows = list(
        db.scalars(
            select(InteractionMessage)
            .where(
                InteractionMessage.interaction_session_id == session.id,
                InteractionMessage.deleted == 0,
            )
            .order_by(
                InteractionMessage.turn_no.asc(),
                InteractionMessage.occurred_at.asc(),
                InteractionMessage.id.asc(),
            )
        ).all()
    )

    messages = [
        MessageItem(
            message_no=row.message_no,
            turn_no=row.turn_no,
            role_type=row.role_type,
            message_type=row.message_type,
            content_text=row.content_text,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]
    return DialogHistoryResponse(
        session_no=session_no, total=len(messages), messages=messages
    )
