"""AI 评估进度服务
作用：以必填、非派生结构化答案和固定人工审核策略计算患者 AI 采集进度。
"""

from __future__ import annotations

import logging
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
from app.services.manual_review_service import build_manual_review_progress

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssessmentProgress:
    """一次 AI 对话评估的结构化进度。"""

    current: int
    total: int
    completed: bool
    answered_question_ids: frozenset[int]
    remaining_question_ids: tuple[int, ...]
    manual_review_question_ids: tuple[int, ...] = ()
    manual_review_pending_question_ids: tuple[int, ...] = ()
    ai_required_question_ids: tuple[int, ...] = ()


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
    """刷新患者 AI 采集进度，但不直接结束患者会话。

    固定人工审核题从一开始计入 current/total，但不进入 AI remaining；
    是否已经由护士填写通过 manual_review_pending_question_ids 单独表达。
    """
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
    required_questions: list[tuple[int, str]] = []
    answered_ids: set[int] = set()
    for instance in instances:
        instance_required_rows = list(
            db.execute(
                select(
                    AssessmentQuestion.id,
                    AssessmentQuestion.question_code,
                )
                .where(
                    AssessmentQuestion.scale_version_id == instance.scale_version_id,
                    AssessmentQuestion.required.is_(True),
                    AssessmentQuestion.derived.is_(False),
                    AssessmentQuestion.deleted == 0,
                )
                .order_by(AssessmentQuestion.sort_no, AssessmentQuestion.id)
            ).all()
        )
        instance_required = [int(row.id) for row in instance_required_rows]
        instance_required_pairs = [
            (int(row.id), str(row.question_code)) for row in instance_required_rows
        ]
        required_questions.extend(instance_required_pairs)
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
        if submission is not None and instance_required:
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

        instance_progress = build_manual_review_progress(
            required_questions=instance_required_pairs,
            answered_question_ids=instance_answered,
        )
        instance_ai_answered = set(instance_progress.ai_required_question_ids).intersection(
            instance_answered
        )
        if submission is not None:
            submission.total_question_count = len(instance_progress.ai_required_question_ids)
            submission.answered_question_count = len(instance_ai_answered)
            submission.submission_status = (
                "completed" if instance_progress.completed else "in_progress"
            )
            submission.submitted_at = (
                datetime.now(UTC)
                if submission.submission_status == "completed"
                else None
            )
            submission.updator = "assessment_progress"
        answered_ids.update(instance_answered)
        instance.instance_status = (
            "ai_completed" if instance_progress.completed else "collecting"
        )
        if instance.instance_status == "ai_completed":
            instance.assessed_at = datetime.now(UTC)
        else:
            instance.assessed_at = None
        instance.updator = "assessment_progress"

    snapshot = build_manual_review_progress(
        required_questions=required_questions,
        answered_question_ids=answered_ids,
    )
    progress = AssessmentProgress(
        current=snapshot.current,
        total=snapshot.total,
        completed=snapshot.completed,
        answered_question_ids=frozenset(answered_ids),
        remaining_question_ids=snapshot.remaining_question_ids,
        manual_review_question_ids=snapshot.manual_review_question_ids,
        manual_review_pending_question_ids=snapshot.manual_review_pending_question_ids,
        ai_required_question_ids=snapshot.ai_required_question_ids,
    )
    db.commit()
    return progress


def complete_assessment_session(db: Session, session_no: str) -> AssessmentProgress:
    """在患者 AI 可采集问题全部完成后结束对话并进入护士复核。"""
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
    if task is not None:
        try:
            from app.celery_app.tasks import nursing_plan_worker

            nursing_plan_worker.delay(task.id, False)
        except Exception:
            logger.exception(
                "护理计划自动生成任务派发失败，不阻塞评估完成: task=%s",
                task.id,
            )
    return progress
