"""护士评估复核服务。
作用：把护士独立确认和最终确认写入多提交评估模型，供画像与护理计划使用。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentInstance,
    AssessmentReview,
    AssessmentSubmission,
)
from app.models.assessment_template import AssessmentQuestion
from app.models.patient_task import CareTask
from app.schemas.assessment_review import AssessmentReviewRequest

logger = logging.getLogger(__name__)


def _load_task(db: Session, task_ref: str, staff_id: int) -> CareTask:
    """加载并校验责任护士任务。"""
    conditions = [CareTask.task_no == task_ref]
    if task_ref.isdigit():
        conditions.append(CareTask.id == int(task_ref))
    task = db.scalar(
        select(CareTask).where(or_(*conditions), CareTask.deleted == 0)
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    if task.assigned_nurse_id is not None and task.assigned_nurse_id != staff_id:
        raise AppError(ErrorCode.ERR_COMMON_001, "当前任务不属于登录医护人员", 403)
    return task


def _question_id_map(db: Session, instance: AssessmentInstance) -> dict[str, int]:
    """支持前端传题目主键或题目编码。"""
    questions = list(
        db.scalars(
            select(AssessmentQuestion).where(
                AssessmentQuestion.scale_version_id == instance.scale_version_id,
                AssessmentQuestion.deleted == 0,
            )
        ).all()
    )
    return {str(question.id): question.id for question in questions} | {
        question.question_code: question.id for question in questions
    }


def _save_submission(
    db: Session,
    instance: AssessmentInstance,
    *,
    submission_type: str,
    answers: dict[str, str],
    staff_id: int,
    completed: bool,
) -> AssessmentSubmission:
    """创建护士独立或最终确认提交，并保存可识别的文本答案。"""
    submission = AssessmentSubmission(
        submission_no=f"SUB-{uuid.uuid4().hex[:16].upper()}",
        assessment_instance_id=instance.id,
        submission_type=submission_type,
        submitter_type="nurse",
        submitter_id=staff_id,
        submission_status="completed" if completed else "in_progress",
        total_question_count=0,
        answered_question_count=0,
        submitted_at=datetime.now(UTC) if completed else None,
        creator=str(staff_id),
        updator=str(staff_id),
    )
    db.add(submission)
    db.flush()
    ids = _question_id_map(db, instance)
    valid_answers = [
        (ids[key], value.strip())
        for key, value in answers.items()
        if key in ids and value is not None and value.strip()
    ]
    for question_id, value in valid_answers:
        db.add(
            AssessmentAnswer(
                submission_id=submission.id,
                question_id=question_id,
                answer_type="text",
                answer_text=value,
                value_source="nurse",
                extraction_confidence=None,
                abnormal_flag=False,
                creator=str(staff_id),
                updator=str(staff_id),
            )
        )
    submission.total_question_count = len(ids)
    submission.answered_question_count = len(valid_answers)
    return submission


def submit_assessment_review(
    db: Session,
    task_ref: str,
    request: AssessmentReviewRequest,
    *,
    staff_id: int,
) -> dict:
    """保存复核结果并在最终确认后触发护理计划重新生成。"""
    task = _load_task(db, task_ref, staff_id)
    instances = list(
        db.scalars(
            select(AssessmentInstance)
            .where(
                AssessmentInstance.task_id == task.id,
                AssessmentInstance.deleted == 0,
            )
            .order_by(AssessmentInstance.id)
        ).all()
    )
    if not instances:
        raise AppError(ErrorCode.ERR_COMMON_001, "当前任务没有可复核的评估实例")

    nurse_submissions: list[AssessmentSubmission] = []
    final_submissions: list[AssessmentSubmission] = []
    for instance in instances:
        nurse_submission = _save_submission(
            db,
            instance,
            submission_type="nurse_independent",
            answers=request.nurse_answers,
            staff_id=staff_id,
            completed=request.status == "confirmed",
        )
        nurse_submissions.append(nurse_submission)
        final_submission = None
        if request.status == "confirmed":
            final_submission = _save_submission(
                db,
                instance,
                submission_type="final_confirmed",
                answers=request.final_answers or request.nurse_answers,
                staff_id=staff_id,
                completed=True,
            )
            final_submissions.append(final_submission)
        ai_submission = db.scalar(
            select(AssessmentSubmission)
            .where(
                AssessmentSubmission.assessment_instance_id == instance.id,
                AssessmentSubmission.submission_type.in_(
                    ["ai_extracted", "ai_extraction", "AI抽取"]
                ),
                AssessmentSubmission.deleted == 0,
            )
            .order_by(AssessmentSubmission.id.desc())
        )
        db.add(
            AssessmentReview(
                review_no=f"REVIEW-{uuid.uuid4().hex[:16].upper()}",
                assessment_instance_id=instance.id,
                ai_submission_id=ai_submission.id if ai_submission else None,
                nurse_submission_id=nurse_submission.id,
                final_submission_id=final_submission.id if final_submission else None,
                reviewer_id=staff_id,
                review_status=request.status,
                supplementary_inquiry=request.supplementary_inquiry or None,
                correction_reason="\n".join(
                    f"{key}: {value}"
                    for key, value in request.correction_reasons.items()
                    if value.strip()
                )
                or None,
                reviewed_at=datetime.now(UTC),
                creator=str(staff_id),
                updator=str(staff_id),
            )
        )

    if request.status == "confirmed":
        task.task_status = "completed"
        task.completed_at = datetime.now(UTC)
        task.updator = str(staff_id)
    db.commit()
    if request.status == "confirmed":
        try:
            from app.celery_app.tasks import nursing_plan_worker

            nursing_plan_worker.delay(task.id, True)
        except Exception:
            # 复核结果已经落库，生成任务失败不应阻塞护士提交。
            logger.exception("护士最终复核后护理计划派发失败: task=%s", task.id)
    return {
        "task_id": task.id,
        "status": request.status,
        "nurse_submission_ids": [item.id for item in nurse_submissions],
        "final_submission_ids": [item.id for item in final_submissions],
    }
