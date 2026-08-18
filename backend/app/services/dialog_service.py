"""对话交互服务
作用：保存患者答案、发布关键词约束与患者事件，并查询完整会话历史。
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
from app.models.assessment_execution import AssessmentInstance
from app.models.assessment_template import AssessmentQuestion
from app.models.interaction import InteractionMessage, InteractionSession
from app.models.patient_task import CareTask
from app.schemas.dialog import (
    DialogHistoryResponse,
    MessageItem,
    SendMessageRequest,
    SendMessageResponse,
)
from app.schemas.events import ConstraintEvent, PatientAnswerEvent
from app.workers.event_publisher import DialogEventPublisher

logger = logging.getLogger(__name__)
_DIALOG_LOCK_TTL = 30


def _load_active_session(db: Session, session_no: str) -> InteractionSession:
    """加载活动会话。"""
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    if session.session_status != "active":
        raise AppError(ErrorCode.ERR_DIALOG_002)
    return session


def _task_matches(task: CareTask, task_ref: int | str) -> bool:
    """判断请求任务标识是否与会话任务一致。"""
    value = str(task_ref)
    return value == str(task.id) or value == task.task_no


def _current_question_turn(db: Session, session_id: int) -> int:
    """获取当前等待患者回答的AI问句轮次。"""
    turn_no = db.scalar(
        select(func.max(InteractionMessage.turn_no)).where(
            InteractionMessage.interaction_session_id == session_id,
            InteractionMessage.role_type == "AI",
            InteractionMessage.deleted == 0,
        )
    )
    if turn_no is None:
        raise AppError(ErrorCode.ERR_DIALOG_002, "AI首个问诊问题尚未就绪，请稍后重试")
    return int(turn_no)


def _publish_constraint(
    publisher: DialogEventPublisher,
    session: InteractionSession,
    task: CareTask,
    matches: list[MatchResult],
) -> None:
    """发布关键词命中的问诊约束。"""
    prompts = [match.constraint_prompt for match in matches if match.constraint_prompt]
    if not prompts:
        return
    publisher.publish(
        ConstraintEvent(
            session_id=session.session_no,
            task_id=task.id,
            constraint_type="keyword_hit",
            constraint_prompt="\n".join(prompts),
            remaining_tasks=[],
        )
    )


async def send_message(
    db: Session,
    req: SendMessageRequest,
    *,
    patient_id: int | None = None,
) -> SendMessageResponse:
    """保存并发布患者答案。"""
    from app.utils.redis_client import get_redis

    session = _load_active_session(db, req.session_id)
    if patient_id is not None and session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权访问该会话")
    task = db.get(CareTask, session.task_id)
    if task is None or not _task_matches(task, req.task_id):
        raise AppError(ErrorCode.ERR_DIALOG_004, "task_id 与会话不匹配")

    existing = db.scalar(
        select(InteractionMessage).where(
            InteractionMessage.message_no == req.client_message_id,
            InteractionMessage.deleted == 0,
        )
    )
    if existing is not None:
        from app.services.agent_dispatch_service import dispatch_answer_workers

        dispatch_answer_workers(
            db,
            session,
            source_message_id=existing.message_no,
            source_event_id=None,
        )
        return SendMessageResponse(
            session_no=req.session_id,
            message_no=existing.message_no,
            turn_no=existing.turn_no,
            intercepted=False,
        )

    redis = get_redis()
    lock_key = f"dialog_lock:{req.session_id}"
    lock_token = uuid.uuid4().hex
    if not redis.acquire_lock(lock_key, lock_token, ttl=_DIALOG_LOCK_TTL):
        raise AppError(ErrorCode.ERR_DIALOG_003)

    try:
        turn_no = _current_question_turn(db, session.id)
        answered = db.scalar(
            select(InteractionMessage.id).where(
                InteractionMessage.interaction_session_id == session.id,
                InteractionMessage.turn_no == turn_no,
                InteractionMessage.role_type.in_(["患者", "家属"]),
                InteractionMessage.deleted == 0,
            )
        )
        if answered is not None:
            raise AppError(ErrorCode.ERR_DIALOG_003, "当前问句已经提交答案")

        message = InteractionMessage(
            interaction_session_id=session.id,
            message_no=req.client_message_id,
            turn_no=turn_no,
            role_type="家属" if session.participant_type == "family" else "患者",
            message_type="文本",
            intent_type="回答",
            content_text=req.content.strip(),
            occurred_at=datetime.now(UTC),
            creator="patient",
            updator="patient",
        )
        db.add(message)
        db.commit()
        db.refresh(message)

        matches = get_keyword_matcher().match(req.content)
        publisher = DialogEventPublisher(session_id=req.session_id)
        _publish_constraint(publisher, session, task, matches)
        answer_event_id = publisher.publish(
            PatientAnswerEvent(
                session_id=req.session_id,
                task_id=task.id,
                message_id=message.message_no,
                turn_number=turn_no,
                role="user",
                content=req.content.strip(),
                client_message_id=req.client_message_id,
                input_mode=req.input_mode,
            )
        )
        from app.services.agent_dispatch_service import dispatch_answer_workers

        dispatch_answer_workers(
            db,
            session,
            source_message_id=message.message_no,
            source_event_id=answer_event_id,
        )
        return SendMessageResponse(
            session_no=req.session_id,
            message_no=message.message_no,
            turn_no=turn_no,
            intercepted=bool(matches),
        )
    finally:
        redis.release_lock(lock_key, lock_token)


async def get_history(
    db: Session,
    session_no: str,
    limit: int = 100,
    offset: int = 0,
    *,
    patient_id: int | None = None,
) -> DialogHistoryResponse:
    """分页查询会话历史与评估进度。"""
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    if patient_id is not None and session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权访问该会话")
    task = db.get(CareTask, session.task_id)
    if task is None:
        raise AppError(ErrorCode.ERR_DIALOG_004)

    base_filter = (
        InteractionMessage.interaction_session_id == session.id,
        InteractionMessage.deleted == 0,
    )
    total = int(db.scalar(select(func.count(InteractionMessage.id)).where(*base_filter)) or 0)
    messages = list(
        db.scalars(
            select(InteractionMessage)
            .where(*base_filter)
            .order_by(
                InteractionMessage.turn_no.asc(),
                InteractionMessage.occurred_at.asc(),
                InteractionMessage.id.asc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
    )
    version_ids = list(
        db.scalars(
            select(AssessmentInstance.scale_version_id).where(
                AssessmentInstance.task_id == task.id,
                AssessmentInstance.deleted == 0,
            )
        ).all()
    )
    total_questions = 0
    if version_ids:
        total_questions = int(
            db.scalar(
                select(func.count(AssessmentQuestion.id)).where(
                    AssessmentQuestion.scale_version_id.in_(version_ids),
                    AssessmentQuestion.derived.is_(False),
                    AssessmentQuestion.deleted == 0,
                )
            )
            or 0
        )
    answered_questions = int(
        db.scalar(
            select(func.count(func.distinct(InteractionMessage.turn_no))).where(
                InteractionMessage.interaction_session_id == session.id,
                InteractionMessage.role_type.in_(["患者", "家属"]),
                InteractionMessage.deleted == 0,
            )
        )
        or 0
    )
    return DialogHistoryResponse(
        session_id=session.session_no,
        task_id=task.id,
        task_no=task.task_no,
        session_status=session.session_status,
        answered_question_count=answered_questions,
        total_question_count=total_questions,
        ai_summary=session.ai_summary,
        total=total,
        messages=[
            MessageItem(
                message_no=message.message_no,
                turn_no=message.turn_no,
                role_type=message.role_type,
                message_type=message.message_type,
                content_text=message.content_text,
                occurred_at=message.occurred_at,
            )
            for message in messages
        ],
    )
