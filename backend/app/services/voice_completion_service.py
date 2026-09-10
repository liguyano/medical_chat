"""实时语音评估完成协调服务。

作用：协调 Extraction Agent 的结构化评估完成和 Qwen Realtime 最后一轮
response.done 两个异步事实。固定人工审核题存在时，还要求系统已经通知护士，
且最终可见语音明确告知患者该人工审核安排，随后才允许结束业务会话。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.models import base as model_base
from app.models.interaction import InteractionMessage, InteractionSession
from app.schemas.events import SessionEndEvent
from app.services.assessment_progress_service import complete_assessment_session
from app.services.manual_review_service import (
    ensure_planned_manual_review_notification,
    load_manual_review_items,
)
from app.utils.redis_client import RedisClient, get_redis
from app.workers.event_publisher import DialogEventPublisher

ASSESSMENT_PENDING_TTL = 24 * 60 * 60
RESPONSE_COMPLETED_TTL = 24 * 60 * 60
FINALIZED_TTL = 7 * 24 * 60 * 60
LOCK_TTL = 30


def _assessment_pending_key(session_no: str) -> str:
    return f"voice_completion_pending:{session_no}"


def _response_completed_key(session_no: str) -> str:
    return f"voice_response_completed:{session_no}"


def _finalized_key(session_no: str) -> str:
    return f"voice_completion_finalized:{session_no}"


def _lock_key(session_no: str) -> str:
    return f"voice_completion_lock:{session_no}"


def _latest_patient_turn(session_no: str) -> int:
    """读取最后一条患者消息的轮次，用于过滤旧响应完成状态。"""
    if model_base.SessionLocal is None:
        return 0
    with model_base.SessionLocal() as db:
        turn_no = db.scalar(
            select(func.max(InteractionMessage.turn_no))
            .join(
                InteractionSession,
                InteractionSession.id == InteractionMessage.interaction_session_id,
            )
            .where(
                InteractionSession.session_no == session_no,
                InteractionSession.deleted == 0,
                InteractionMessage.deleted == 0,
                InteractionMessage.role_type.in_(["患者", "patient"]),
            )
        )
    return int(turn_no or 0)


def _manual_review_item_count(session_no: str) -> int:
    """读取当前会话固定人工审核题数量；无数据库运行态视为无固定审核。"""
    if model_base.SessionLocal is None:
        return 0
    with model_base.SessionLocal() as db:
        session = db.scalar(
            select(InteractionSession).where(
                InteractionSession.session_no == session_no,
                InteractionSession.deleted == 0,
            )
        )
        if session is None:
            return 0
        return len(load_manual_review_items(db, session.task_id))


def _is_manual_review_completion_response(
    session_no: str,
    response_turn: int,
) -> bool:
    """验证某轮可见 AI 语音是否真的完成了固定人工审核结束播报。

    这是后端输出校验，不由模型决定是否需要人工审核。只有同时明确提到护士、
    人工审核/核实以及“已通知”语义的已持久化 AI 文本才满足完成屏障。
    """
    if model_base.SessionLocal is None:
        return False
    with model_base.SessionLocal() as db:
        text = db.scalar(
            select(InteractionMessage.content_text)
            .join(
                InteractionSession,
                InteractionSession.id == InteractionMessage.interaction_session_id,
            )
            .where(
                InteractionSession.session_no == session_no,
                InteractionSession.deleted == 0,
                InteractionMessage.deleted == 0,
                InteractionMessage.turn_no == response_turn,
                InteractionMessage.role_type.in_(["AI", "assistant"]),
            )
            .order_by(InteractionMessage.id.desc())
            .limit(1)
        )
    content = str(text or "").strip()
    if not content:
        return False
    has_manual_review = "人工审核" in content or "人工核实" in content
    has_nurse = "护士" in content
    has_notified = any(
        marker in content
        for marker in ("已经通知", "已通知", "已经告知", "已告知")
    )
    return has_manual_review and has_nurse and has_notified


def finalize_voice_assessment_session(
    *,
    session_id: str,
    task_id: int | str | None,
) -> bool:
    """完成数据库会话并发布任务结束事件。

    Return:
        - True：本次会话已经完成，或本次调用成功完成并发布事件。
        - False：结构化进度尚未完整，调用方应保留等待状态。
    """
    if model_base.SessionLocal is None:
        raise RuntimeError("数据库未初始化")

    with model_base.SessionLocal() as db:
        session = db.scalar(
            select(InteractionSession).where(
                InteractionSession.session_no == session_id,
                InteractionSession.deleted == 0,
            )
        )
        if session is None:
            raise RuntimeError(f"交互会话不存在: {session_id}")

        progress = complete_assessment_session(db, session_id)
        total_turns = int(
            db.scalar(
                select(func.max(InteractionMessage.turn_no)).where(
                    InteractionMessage.interaction_session_id == session.id,
                    InteractionMessage.deleted == 0,
                )
            )
            or 0
        )
        resolved_task_id = task_id if task_id is not None else session.task_id

    if not progress.completed:
        return False

    DialogEventPublisher(session_id).publish(
        SessionEndEvent(
            event_id=f"VOICE-SESSION-END-{session_id}",
            session_id=session_id,
            task_id=resolved_task_id,
            message_id=None,
            end_reason="completed",
            total_turns=total_turns,
            duration_seconds=0,
        )
    )
    return True


class VoiceCompletionCoordinator:
    """跨 Celery Worker 与 Voice Gateway 的语音完成屏障。"""

    def __init__(self, redis: RedisClient | Any | None = None) -> None:
        self.redis = redis or get_redis()

    def mark_assessment_completed(
        self,
        *,
        session_id: str,
        task_id: int | str | None,
    ) -> bool:
        """登记 Extraction 完成；固定人工审核在此时由系统通知护士。"""
        patient_turn = _latest_patient_turn(session_id)
        manual_review_count = _manual_review_item_count(session_id)
        manual_review_notified = manual_review_count == 0
        if manual_review_count > 0:
            notification = ensure_planned_manual_review_notification(session_id)
            manual_review_count = notification.item_count
            manual_review_notified = bool(notification.notified)
            if not manual_review_notified:
                raise RuntimeError("固定人工审核护士通知未成功创建")

        self.redis.set(
            _assessment_pending_key(session_id),
            {
                "task_id": task_id,
                "minimum_response_turn": patient_turn + 1 if patient_turn else 0,
                "manual_review_count": manual_review_count,
                "manual_review_notified": manual_review_notified,
            },
            ex=ASSESSMENT_PENDING_TTL,
        )
        return self._try_finalize(session_id)

    def mark_response_completed(
        self,
        *,
        session_id: str,
        task_id: int | str | None,
        response_turn: int,
        response_id: str | None = None,
        generation_id: str | None = None,
    ) -> bool:
        """登记一轮可见 AI 回复完成，并在评估已完成时尝试收尾。"""
        key = _response_completed_key(session_id)
        existing = self.redis.get(key)
        previous_turn = (
            int(existing.get("response_turn") or 0)
            if isinstance(existing, dict)
            else 0
        )
        if response_turn >= previous_turn:
            self.redis.set(
                key,
                {
                    "task_id": task_id,
                    "response_turn": response_turn,
                    "response_id": response_id,
                    "generation_id": generation_id,
                },
                ex=RESPONSE_COMPLETED_TTL,
            )
        return self._try_finalize(session_id)

    def _try_finalize(self, session_id: str) -> bool:
        """满足结构化完成、最终播报和固定人工审核通知后幂等收尾。"""
        token = uuid.uuid4().hex
        if not self.redis.acquire_lock(
            _lock_key(session_id),
            token,
            ttl=LOCK_TTL,
        ):
            return False
        try:
            if self.redis.exists(_finalized_key(session_id)):
                return True
            pending = self.redis.get(_assessment_pending_key(session_id))
            response = self.redis.get(_response_completed_key(session_id))
            if not isinstance(pending, dict) or not isinstance(response, dict):
                return False
            minimum_turn = int(pending.get("minimum_response_turn") or 0)
            response_turn = int(response.get("response_turn") or 0)
            if response_turn < minimum_turn:
                return False

            manual_review_count = int(pending.get("manual_review_count") or 0)
            if manual_review_count > 0:
                if not bool(pending.get("manual_review_notified")):
                    return False
                if not _is_manual_review_completion_response(
                    session_id,
                    response_turn,
                ):
                    return False

            finalized = finalize_voice_assessment_session(
                session_id=session_id,
                task_id=pending.get("task_id"),
            )
            if finalized:
                self.redis.set(
                    _finalized_key(session_id),
                    {
                        "task_id": pending.get("task_id"),
                        "response_turn": response_turn,
                        "generation_id": response.get("generation_id"),
                    },
                    ex=FINALIZED_TTL,
                )
            return finalized
        finally:
            self.redis.release_lock(_lock_key(session_id), token)


def mark_voice_assessment_completed(
    *,
    session_id: str,
    task_id: int | str | None,
    redis: RedisClient | Any | None = None,
) -> bool:
    """登记 Extraction 完成。"""
    return VoiceCompletionCoordinator(redis).mark_assessment_completed(
        session_id=session_id,
        task_id=task_id,
    )


def mark_voice_response_completed(
    *,
    session_id: str,
    task_id: int | str | None,
    response_turn: int,
    response_id: str | None = None,
    generation_id: str | None = None,
    redis: RedisClient | Any | None = None,
) -> bool:
    """登记 Qwen Realtime 可见回复完成。"""
    return VoiceCompletionCoordinator(redis).mark_response_completed(
        session_id=session_id,
        task_id=task_id,
        response_turn=response_turn,
        response_id=response_id,
        generation_id=generation_id,
    )
