"""AI 评估进度服务
作用：以必填、非派生结构化答案为唯一事实来源计算进度和完成条件。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentInstance,
    AssessmentSubmission,
)
from app.models.assessment_template import AssessmentQuestion
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask


@dataclass(frozen=True)
class AssessmentProgress:
    """一次 AI 对话评估的结构化进度。"""

    current: int
    total: int
    completed: bool
    answered_question_ids: frozenset[int]
    remaining_question_ids: tuple[int, ...]


MIN_VALID_EXTRACTION_CONFIDENCE = Decimal("0.6")


def valid_assessment_answer_condition() -> ColumnElement[bool]:
    """构建有效结构化答案条件。
    作用：空答案、空文本和低置信度 AI 抽取不得推进完成进度；
    布尔 False、数值 0、日期时间和有效选择项均属于有效答案。
    """
    has_value = or_(
        and_(
            AssessmentAnswer.answer_text.is_not(None),
            func.length(func.trim(AssessmentAnswer.answer_text)) > 0,
        ),
        AssessmentAnswer.answer_number.is_not(None),
        AssessmentAnswer.answer_boolean.is_not(None),
        AssessmentAnswer.answer_date.is_not(None),
        AssessmentAnswer.answer_time.is_not(None),
        AssessmentAnswer.answer_datetime.is_not(None),
        exists(
            select(AssessmentAnswerOption.id).where(
                AssessmentAnswerOption.assessment_answer_id == AssessmentAnswer.id,
                AssessmentAnswerOption.selected_flag.is_(True),
                AssessmentAnswerOption.deleted == 0,
            )
        ),
    )
    confidence_is_acceptable = or_(
        AssessmentAnswer.extraction_confidence.is_(None),
        AssessmentAnswer.extraction_confidence
        >= MIN_VALID_EXTRACTION_CONFIDENCE,
    )
    return and_(has_value, confidence_is_acceptable)


def refresh_assessment_progress(
    db: Session,
    session_no: str,
) -> AssessmentProgress:
    """刷新提交与实例进度，但不直接结束患者会话。"""
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise RuntimeError(f"交互会话不存在: {session_no}")

    instances = list(
        db.scalars(
            select(AssessmentInstance)
            .where(
                AssessmentInstance.task_id == session.task_id,
                AssessmentInstance.deleted == 0,
            )
            .order_by(AssessmentInstance.id)
        ).all()
    )
    required_ids: list[int] = []
    answered_ids: set[int] = set()
    for instance in instances:
        instance_required = list(
            db.scalars(
                select(AssessmentQuestion.id)
                .where(
                    AssessmentQuestion.scale_version_id == instance.scale_version_id,
                    AssessmentQuestion.required.is_(True),
                    AssessmentQuestion.derived.is_(False),
                    AssessmentQuestion.deleted == 0,
                )
                .order_by(AssessmentQuestion.sort_no, AssessmentQuestion.id)
            ).all()
        )
        required_ids.extend(instance_required)
        submission = db.scalar(
            select(AssessmentSubmission)
            .where(
                AssessmentSubmission.assessment_instance_id == instance.id,
                AssessmentSubmission.interaction_session_id == session.id,
                AssessmentSubmission.deleted == 0,
            )
            .order_by(AssessmentSubmission.id.desc())
        )
        instance_answered: set[int] = set()
        if submission is not None:
            instance_answered = set(
                db.scalars(
                    select(AssessmentAnswer.question_id).where(
                        AssessmentAnswer.submission_id == submission.id,
                        AssessmentAnswer.question_id.in_(instance_required),
                        AssessmentAnswer.deleted == 0,
                        valid_assessment_answer_condition(),
                    )
                ).all()
            )
            submission.total_question_count = len(instance_required)
            submission.answered_question_count = len(instance_answered)
            submission.submission_status = (
                "completed"
                if len(instance_answered) == len(instance_required)
                else "in_progress"
            )
            submission.submitted_at = (
                datetime.now(UTC)
                if submission.submission_status == "completed"
                else None
            )
            submission.updator = "assessment_progress"
        answered_ids.update(instance_answered)
        instance.instance_status = (
            "ai_completed"
            if len(instance_answered) == len(instance_required)
            else "collecting"
        )
        if instance.instance_status == "ai_completed":
            instance.assessed_at = datetime.now(UTC)
        instance.updator = "assessment_progress"

    ordered_required = list(dict.fromkeys(required_ids))
    remaining = tuple(
        question_id
        for question_id in ordered_required
        if question_id not in answered_ids
    )
    progress = AssessmentProgress(
        current=len(answered_ids),
        total=len(ordered_required),
        completed=bool(ordered_required) and not remaining,
        answered_question_ids=frozenset(answered_ids),
        remaining_question_ids=remaining,
    )
    db.commit()
    return progress


def complete_assessment_session(db: Session, session_no: str) -> AssessmentProgress:
    """在进度完整后完成会话、任务和评估实例。"""
    progress = refresh_assessment_progress(db, session_no)
    if not progress.completed:
        return progress
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise RuntimeError(f"交互会话不存在: {session_no}")
    task = db.get(CareTask, session.task_id)
    now = datetime.now(UTC)
    session.session_status = "completed"
    session.ended_at = now
    session.updator = "assessment_progress"
    if task is not None:
        task.task_status = "pending_review"
        task.completed_at = now
        task.updator = "assessment_progress"
    db.commit()
    return progress
