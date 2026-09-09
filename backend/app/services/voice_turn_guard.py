"""实时语音回合语义守卫。

作用：在患者已经听完 Qwen Realtime 一轮回复后，识别明确的提前结束话术，
等待本轮 Extraction Agent 完成结构化处理，再以结构化评估进度决定是否需要恢复。
该模块不做输出前拦截，也不负责生成患者可见文案。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from medagent.agents.service_agent.schedule_agent import QuestionTask
from sqlalchemy import select

from app.models import base as model_base
from app.models.interaction import InteractionMessage, InteractionSession
from app.services.assessment_progress_service import AssessmentProgress, refresh_assessment_progress

# 明确表达“当前评估已经结束”的话术。单独的“谢谢/感谢配合”不算结束，降低误判。
_CLOSING_PATTERNS = (
    re.compile(r"(?:本次|这次|此次|今天)?(?:入院)?(?:评估|问诊)(?:已经|已|就|先|可以)?(?:完成|结束|到这里|告一段落)"),
    re.compile(r"(?:本次|这次|此次|今天)(?:的)?(?:评估|问诊)?(?:就|先)?到这里"),
    re.compile(r"(?:问题|内容)(?:都|已经|已)?(?:问完|完成|结束)"),
    re.compile(r"(?:感谢|谢谢).{0,12}配合.{0,12}(?:评估|问诊).{0,8}(?:完成|结束|到这里)"),
)

# 明确否定“现在结束”的语义时不触发，例如“评估还没有完成，我们继续下一项”。
_NOT_CLOSING_PATTERNS = (
    re.compile(r"(?:尚未|还未|还没有|还没|未)(?:完成|结束)"),
    re.compile(r"(?:不能|不要|不会|不应|不可)(?:现在)?(?:结束|完成)"),
    re.compile(r"(?:还需要|还要|继续)(?:确认|询问|问|完成|进行)"),
)


@dataclass(frozen=True)
class VoiceRecoveryDecision:
    """提前结束后的恢复决策。"""

    progress: AssessmentProgress
    next_question: QuestionTask | None

    @property
    def should_recover(self) -> bool:
        return not self.progress.completed and self.next_question is not None


class VoiceTurnGuard:
    """Qwen Realtime 患者可见回复的事后语义守卫。"""

    @staticmethod
    def has_closing_intent(text: str) -> bool:
        """判断一条完整 AI 回复是否明确宣告当前评估结束。"""
        normalized = re.sub(r"\s+", "", str(text or "")).strip()
        if not normalized:
            return False
        if any(pattern.search(normalized) for pattern in _NOT_CLOSING_PATTERNS):
            return False
        return any(pattern.search(normalized) for pattern in _CLOSING_PATTERNS)

    @staticmethod
    def latest_patient_message_no(session_no: str) -> str | None:
        """读取当前会话最新一条患者正式消息编号。"""
        if model_base.SessionLocal is None:
            return None
        with model_base.SessionLocal() as db:
            message_no = db.scalar(
                select(InteractionMessage.message_no)
                .join(
                    InteractionSession,
                    InteractionSession.id == InteractionMessage.interaction_session_id,
                )
                .where(
                    InteractionSession.session_no == session_no,
                    InteractionSession.deleted == 0,
                    InteractionMessage.deleted == 0,
                    InteractionMessage.role_type.in_(["患者", "家属", "user", "patient"]),
                )
                .order_by(InteractionMessage.turn_no.desc(), InteractionMessage.id.desc())
                .limit(1)
            )
        return str(message_no) if message_no else None

    @staticmethod
    def extraction_processed(
        redis: Any,
        session_no: str,
        source_message_no: str | None,
    ) -> bool:
        """确认 Extraction Agent 已处理本轮患者消息，避免读取到落库前的旧进度。"""
        if source_message_no is None:
            return True
        state = redis.get(f"extraction_agent:state:{session_no}")
        if not isinstance(state, dict):
            return False
        processed = state.get("processed_message_ids") or []
        return source_message_no in processed

    @staticmethod
    def build_recovery_decision(
        session_no: str,
        task_list: Iterable[QuestionTask],
    ) -> VoiceRecoveryDecision:
        """刷新权威结构化进度，并按原 Task-todo 顺序选择一条未完成必填题。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            progress = refresh_assessment_progress(db, session_no)
        remaining = set(progress.remaining_question_ids)
        next_question = next(
            (question for question in task_list if question.question_id in remaining),
            None,
        )
        return VoiceRecoveryDecision(
            progress=progress,
            next_question=next_question,
        )
