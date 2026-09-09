"""实时语音回合语义守卫。

作用：在患者已经听完 Qwen Realtime 一轮回复后，识别明确的提前结束话术，
等待本轮 Extraction Agent 完成结构化处理，再以结构化评估进度决定是否需要恢复。
该模块不做输出前拦截，也不负责生成患者可见文案。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from medagent.agents.service_agent.schedule_agent import QuestionOption, QuestionTask
from sqlalchemy import select

from app.models import base as model_base
from app.models.assessment_template import (
    AssessmentOption,
    AssessmentQuestion,
    AssessmentSection,
)
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
    def _load_question_task_from_db(db: Any, question_id: int) -> QuestionTask | None:
        """按 question_id 从当前数据库模板域恢复一条可问问题。

        用于 Redis Schedule plan 过期、缺题或使用旧 question_id 时的兜底。question_id
        来自 assessment_progress 的 remaining 集合，因此仍由当前任务绑定的结构化评估事实
        决定是否允许询问。
        """
        row = db.execute(
            select(AssessmentQuestion, AssessmentSection.section_name)
            .outerjoin(
                AssessmentSection,
                AssessmentSection.id == AssessmentQuestion.section_id,
            )
            .where(
                AssessmentQuestion.id == question_id,
                AssessmentQuestion.required.is_(True),
                AssessmentQuestion.derived.is_(False),
                AssessmentQuestion.deleted == 0,
            )
        ).first()
        if row is None:
            return None

        question, section_name = row
        options = list(
            db.scalars(
                select(AssessmentOption)
                .where(
                    AssessmentOption.question_id == question_id,
                    AssessmentOption.deleted == 0,
                )
                .order_by(AssessmentOption.sort_no, AssessmentOption.id)
            ).all()
        )
        return QuestionTask(
            question_id=question.id,
            question_code=question.question_code,
            question_name=question.question_name,
            patient_text=question.patient_text,
            question_type=question.question_type,
            required=question.required,
            sort_no=question.sort_no,
            section_name=section_name,
            options=[
                QuestionOption(
                    option_code=option.option_code,
                    option_label=option.option_label,
                    option_value=option.option_value,
                    clinical_score=(
                        float(option.clinical_score)
                        if option.clinical_score is not None
                        else None
                    ),
                    requires_follow_up=option.requires_follow_up,
                )
                for option in options
            ],
        )

    @staticmethod
    def build_recovery_decision(
        session_no: str,
        task_list: Iterable[QuestionTask],
    ) -> VoiceRecoveryDecision:
        """刷新权威结构化进度，并选择一条未完成必填题。

        优先保留 Schedule plan 的原有排序；若 Redis 中的 plan 已过期、缺题或 question_id
        与当前评估实例不一致，则直接按 remaining_question_ids 从 PostgreSQL 当前题目快照
        恢复问题文本。不得因为 Redis 缓存不一致而退回完整题表。
        """
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            progress = refresh_assessment_progress(db, session_no)
            remaining = set(progress.remaining_question_ids)
            next_question = next(
                (question for question in task_list if question.question_id in remaining),
                None,
            )
            if next_question is None and progress.remaining_question_ids:
                for question_id in progress.remaining_question_ids:
                    next_question = VoiceTurnGuard._load_question_task_from_db(
                        db,
                        question_id,
                    )
                    if next_question is not None:
                        break
        return VoiceRecoveryDecision(
            progress=progress,
            next_question=next_question,
        )
