"""护士 AI 质量评价服务。
作用：校验任务/会话/消息归属，保存逐条消息质评与整体质量评价，并提供查询汇总。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import AssessmentInstance, AssessmentSubmission
from app.models.interaction import InteractionMessage, InteractionMessageFeedback, InteractionSession
from app.models.patient_task import CareTask
from app.models.quality_review import (
    QualityReview,
    QualityReviewDimension,
    QualityReviewScore,
    QualityReviewTemplate,
)
from app.schemas.quality import (
    MessageRatingListResponse,
    MessageRatingRequest,
    MessageRatingResponse,
    QualityReviewRequest,
    QualityReviewResponse,
)

AI_DIALOGUE_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("cicare", "CICARE规范性"),
    ("information_accuracy", "信息准确性"),
    ("inquiry_completeness", "问询完整性"),
    ("follow_up_reasonableness", "追问合理性"),
    ("education_appropriateness", "宣教适宜性"),
    ("communication_friendliness", "沟通友好度"),
    ("safety", "安全性"),
)

AI_ASSESSMENT_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("answer_extraction_accuracy", "答案抽取准确性"),
    ("answer_completeness", "答案完整性"),
    ("clinical_scoring_correctness", "临床计分正确性"),
    ("risk_identification_correctness", "风险识别正确性"),
    ("care_recommendation_match", "护理建议匹配度"),
)


def _resolve_task(db: Session, task_ref: int | str) -> CareTask:
    """按任务主键或业务编号获取任务。"""
    task_ref_text = str(task_ref)
    conditions = [CareTask.task_no == task_ref_text]
    if task_ref_text.isdigit():
        conditions.append(CareTask.id == int(task_ref_text))
    task = db.scalar(
        select(CareTask).where(
            or_(*conditions),
            CareTask.deleted == 0,
        )
    )
    if task is None:
        raise AppError(ErrorCode.ERR_QUALITY_001)
    return task


def _resolve_session(db: Session, task: CareTask) -> InteractionSession:
    """获取任务最新的 AI 对话会话。"""
    session = db.scalar(
        select(InteractionSession)
        .where(
            InteractionSession.task_id == task.id,
            InteractionSession.deleted == 0,
        )
        .order_by(InteractionSession.id.desc())
    )
    if session is None:
        raise AppError(ErrorCode.ERR_QUALITY_002)
    return session


def _resolve_message(
    db: Session,
    session: InteractionSession,
    message_ref: int | str,
) -> InteractionMessage:
    """按消息主键或编号获取当前会话中的 AI 消息。"""
    message_ref_text = str(message_ref)
    conditions = [InteractionMessage.message_no == message_ref_text]
    if message_ref_text.isdigit():
        conditions.append(InteractionMessage.id == int(message_ref_text))
    message = db.scalar(
        select(InteractionMessage).where(
            InteractionMessage.interaction_session_id == session.id,
            InteractionMessage.deleted == 0,
            or_(*conditions),
        )
    )
    if message is None:
        raise AppError(ErrorCode.ERR_QUALITY_003)
    if message.role_type.lower() not in {"ai", "assistant", "agent"}:
        raise AppError(ErrorCode.ERR_QUALITY_004)
    return message


def _assessment_target_id(db: Session, task: CareTask) -> int | None:
    """获取任务最新的 AI 评估提交，作为整体评估质评目标。"""
    return db.scalar(
        select(AssessmentSubmission.id)
        .join(
            AssessmentInstance,
            AssessmentInstance.id == AssessmentSubmission.assessment_instance_id,
        )
        .where(
            AssessmentInstance.task_id == task.id,
            AssessmentInstance.deleted == 0,
            AssessmentSubmission.deleted == 0,
            AssessmentSubmission.submission_type.in_(
                ("ai_extracted", "ai_extraction", "AI抽取")
            ),
            AssessmentSubmission.submission_status.in_(
                ("completed", "submitted", "已完成", "已提交")
            ),
        )
        .order_by(AssessmentSubmission.id.desc())
    )


def _now() -> datetime:
    """返回带时区的当前时间。"""
    return datetime.now(UTC)


def _rating_from_score(score: int | None, rating: str | None) -> str:
    """将分值转换为兼容旧接口的 like/dislike。"""
    if rating is not None:
        return rating
    return "like" if score is not None and score >= 4 else "dislike"


def submit_message_rating(
    db: Session,
    request: MessageRatingRequest,
) -> MessageRatingResponse:
    """新增或更新护士对单条 AI 消息的质评。"""
    task = _resolve_task(db, request.task_id)
    session = _resolve_session(db, task)
    message = _resolve_message(db, session, request.message_id)
    reviewed_at = _now()

    feedback = db.scalar(
        select(InteractionMessageFeedback).where(
            InteractionMessageFeedback.interaction_message_id == message.id,
            InteractionMessageFeedback.reviewer_id == request.reviewer_id,
            InteractionMessageFeedback.deleted == 0,
        )
    )
    if feedback is None:
        feedback = InteractionMessageFeedback(
            interaction_session_id=session.id,
            interaction_message_id=message.id,
            turn_no=message.turn_no,
            reviewer_id=request.reviewer_id,
            creator=str(request.reviewer_id),
        )
        db.add(feedback)

    feedback.feedback_type = _rating_from_score(request.score, request.rating)
    feedback.score = request.score
    feedback.issue_tags = list(dict.fromkeys(request.issue_tags))
    feedback.comment = request.comment
    feedback.reviewed_at = reviewed_at
    feedback.updator = str(request.reviewer_id)
    db.commit()
    db.refresh(feedback)
    return _to_message_rating_response(task, message, feedback)


def list_message_ratings(
    db: Session,
    task_ref: int | str,
    reviewer_id: int = 0,
) -> MessageRatingListResponse:
    """查询任务下当前护士的全部逐条质评。"""
    task = _resolve_task(db, task_ref)
    session = _resolve_session(db, task)
    rows = db.scalars(
        select(InteractionMessageFeedback)
        .join(
            InteractionMessage,
            InteractionMessage.id == InteractionMessageFeedback.interaction_message_id,
        )
        .where(
            InteractionMessageFeedback.interaction_session_id == session.id,
            InteractionMessageFeedback.reviewer_id == reviewer_id,
            InteractionMessageFeedback.deleted == 0,
            InteractionMessage.deleted == 0,
        )
        .order_by(InteractionMessageFeedback.reviewed_at.asc(), InteractionMessageFeedback.id.asc())
    ).all()
    message_by_id = {
        message.id: message
        for message in db.scalars(
            select(InteractionMessage).where(
                InteractionMessage.interaction_session_id == session.id,
                InteractionMessage.deleted == 0,
            )
        ).all()
    }
    return MessageRatingListResponse(
        items=[
            _to_message_rating_response(task, message_by_id[row.interaction_message_id], row)
            for row in rows
            if row.interaction_message_id in message_by_id
        ]
    )


def _to_message_rating_response(
    task: CareTask,
    message: InteractionMessage,
    feedback: InteractionMessageFeedback,
) -> MessageRatingResponse:
    """转换逐条质评响应。"""
    return MessageRatingResponse(
        feedback_id=feedback.id,
        task_id=str(task.id),
        message_id=message.message_no,
        reviewer_id=feedback.reviewer_id,
        rating=feedback.feedback_type,
        score=feedback.score,
        issue_tags=feedback.issue_tags or [],
        comment=feedback.comment,
        reviewed_at=feedback.reviewed_at,
    )


def _template_dimensions(
    db: Session,
    *,
    template_code: str,
    template_name: str,
    target_type: str,
    dimensions: Iterable[tuple[str, str]],
) -> tuple[QualityReviewTemplate, dict[str, QualityReviewDimension]]:
    """获取或创建默认模板及维度。"""
    template = db.scalar(
        select(QualityReviewTemplate).where(
            QualityReviewTemplate.template_code == template_code,
            QualityReviewTemplate.version_code == "v1",
            QualityReviewTemplate.deleted == 0,
        )
    )
    if template is None:
        template = QualityReviewTemplate(
            template_code=template_code,
            template_name=template_name,
            target_type=target_type,
            score_scale="1-5",
            version_code="v1",
            status="enabled",
            creator="system",
            updator="system",
        )
        db.add(template)
        db.flush()

    existing = db.scalars(
        select(QualityReviewDimension).where(
            QualityReviewDimension.template_id == template.id,
            QualityReviewDimension.deleted == 0,
        )
    ).all()
    by_key = {
        key: dimension
        for dimension in existing
        for key in (dimension.dimension_code, dimension.dimension_name)
    }
    for sort_no, (dimension_code, dimension_name) in enumerate(dimensions, start=1):
        if dimension_code in by_key or dimension_name in by_key:
            continue
        dimension = QualityReviewDimension(
            template_id=template.id,
            dimension_code=dimension_code,
            dimension_name=dimension_name,
            dimension_description="护士对 AI 表现进行 1～5 分评价",
            weight=Decimal("1"),
            max_score=Decimal("5"),
            sort_no=sort_no,
            creator="system",
            updator="system",
        )
        db.add(dimension)
        db.flush()
        by_key[dimension_code] = dimension
        by_key[dimension_name] = dimension
    return template, by_key


def _ensure_dimensions(
    db: Session,
) -> tuple[
    tuple[QualityReviewTemplate, dict[str, QualityReviewDimension]],
    tuple[QualityReviewTemplate, dict[str, QualityReviewDimension]],
]:
    """确保对话质量和评估质量模板存在。"""
    dialogue = _template_dimensions(
        db,
        template_code="ai_dialogue_quality",
        template_name="AI对话质量",
        target_type="ai_dialogue",
        dimensions=AI_DIALOGUE_DIMENSIONS,
    )
    assessment = _template_dimensions(
        db,
        template_code="ai_assessment_quality",
        template_name="AI评估质量",
        target_type="ai_assessment",
        dimensions=AI_ASSESSMENT_DIMENSIONS,
    )
    return dialogue, assessment


def _find_or_create_dimension(
    db: Session,
    template: QualityReviewTemplate,
    dimensions: dict[str, QualityReviewDimension],
    key: str,
) -> QualityReviewDimension:
    """允许前端使用维度编码或中文名称，未知维度也可扩展保存。"""
    if key in dimensions:
        return dimensions[key]
    dimension = QualityReviewDimension(
        template_id=template.id,
        dimension_code=f"custom_{uuid.uuid4().hex[:12]}",
        dimension_name=key,
        dimension_description="自定义质量评价维度",
        weight=Decimal("1"),
        max_score=Decimal("5"),
        sort_no=len(dimensions) + 1,
        creator="system",
        updator="system",
    )
    db.add(dimension)
    db.flush()
    dimensions[key] = dimension
    return dimension


def _upsert_quality_review(
    db: Session,
    *,
    task: CareTask,
    template: QualityReviewTemplate,
    dimensions: dict[str, QualityReviewDimension],
    target_type: str,
    target_id: int,
    reviewer_id: int,
    scores: dict[str, int],
    comments: dict[str, str],
    evidence_message_ids: dict[str, list[str]],
    evidence_question_ids: dict[str, list[str]],
    review_comment: str | None,
    reviewed_at: datetime,
) -> QualityReview | None:
    """保存一组整体评价维度。"""
    if not scores:
        return None
    review = db.scalar(
        select(QualityReview).where(
            QualityReview.target_type == target_type,
            QualityReview.target_id == target_id,
            QualityReview.reviewer_id == reviewer_id,
            QualityReview.deleted == 0,
        )
    )
    if review is None:
        review = QualityReview(
            review_no=f"QR-{uuid.uuid4().hex[:16].upper()}",
            template_id=template.id,
            target_type=target_type,
            target_id=target_id,
            patient_id=task.patient_id,
            encounter_id=task.encounter_id,
            reviewer_id=reviewer_id,
            creator=str(reviewer_id),
        )
        db.add(review)
        db.flush()

    review.template_id = template.id
    review.overall_score = Decimal(str(round(sum(scores.values()) / len(scores), 2)))
    review.review_comment = review_comment or ""
    review.issue_tags = []
    review.reviewed_at = reviewed_at
    review.updator = str(reviewer_id)

    existing_scores = {
        row.dimension_id: row
        for row in db.scalars(
            select(QualityReviewScore).where(
                QualityReviewScore.quality_review_id == review.id,
                QualityReviewScore.deleted == 0,
            )
        ).all()
    }
    for key, score in scores.items():
        dimension = _find_or_create_dimension(db, template, dimensions, key)
        score_row = existing_scores.get(dimension.id)
        if score_row is None:
            score_row = QualityReviewScore(
                quality_review_id=review.id,
                dimension_id=dimension.id,
                creator=str(reviewer_id),
            )
            db.add(score_row)
        score_row.score_value = Decimal(str(score))
        score_row.score_comment = comments.get(key, "")
        score_row.evidence_message_ids = evidence_message_ids.get(key, [])
        score_row.evidence_question_ids = evidence_question_ids.get(key, [])
        score_row.updator = str(reviewer_id)
    return review


def submit_quality_review(
    db: Session,
    request: QualityReviewRequest,
) -> QualityReviewResponse:
    """保存任务的 AI 对话质量和 AI 评估质量评价。"""
    task = _resolve_task(db, request.task_id)
    session = _resolve_session(db, task)
    (dialogue_template, dialogue_dimensions), (
        assessment_template,
        assessment_dimensions,
    ) = _ensure_dimensions(db)
    reviewed_at = _now()
    assessment_target_id = _assessment_target_id(db, task)
    if request.assessment_scores and assessment_target_id is None:
        raise AppError(ErrorCode.ERR_QUALITY_005)
    _upsert_quality_review(
        db,
        task=task,
        template=dialogue_template,
        dimensions=dialogue_dimensions,
        target_type="ai_dialogue",
        target_id=session.id,
        reviewer_id=request.reviewer_id,
        scores=request.dialogue_scores,
        comments=request.dialogue_comments,
        evidence_message_ids=request.evidence_message_ids,
        evidence_question_ids=request.evidence_question_ids,
        review_comment=request.comment,
        reviewed_at=reviewed_at,
    )
    _upsert_quality_review(
        db,
        task=task,
        template=assessment_template,
        dimensions=assessment_dimensions,
        target_type="ai_assessment",
        target_id=assessment_target_id or 0,
        reviewer_id=request.reviewer_id,
        scores=request.assessment_scores,
        comments=request.assessment_comments,
        evidence_message_ids={},
        evidence_question_ids=request.evidence_question_ids,
        review_comment=request.comment,
        reviewed_at=reviewed_at,
    )
    db.commit()
    return get_quality_review(db, task.id, request.reviewer_id, resolve_task=False) or QualityReviewResponse(
        task_id=str(task.id),
        reviewer_id=request.reviewer_id,
        submitted_at=reviewed_at,
    )


def _review_scores(
    db: Session,
    review: QualityReview | None,
) -> tuple[dict[str, float], dict[str, str]]:
    """读取总体评价的分项得分与意见。"""
    if review is None:
        return {}, {}
    rows = db.execute(
        select(QualityReviewScore, QualityReviewDimension)
        .join(
            QualityReviewDimension,
            QualityReviewDimension.id == QualityReviewScore.dimension_id,
        )
        .where(
            QualityReviewScore.quality_review_id == review.id,
            QualityReviewScore.deleted == 0,
            QualityReviewDimension.deleted == 0,
        )
    ).all()
    scores = {
        dimension.dimension_name: float(score.score_value)
        for score, dimension in rows
        if score.score_value is not None
    }
    comments = {
        dimension.dimension_name: score.score_comment
        for score, dimension in rows
        if score.score_comment
    }
    return scores, comments


def get_quality_review(
    db: Session,
    task_ref: int | str,
    reviewer_id: int = 0,
    *,
    resolve_task: bool = True,
) -> QualityReviewResponse | None:
    """读取当前护士对任务的整体质量评价。"""
    task = _resolve_task(db, task_ref) if resolve_task else db.get(CareTask, int(task_ref))
    if task is None:
        return None
    session = _resolve_session(db, task)
    assessment_target_id = _assessment_target_id(db, task)
    dialogue_review = db.scalar(
        select(QualityReview).where(
            QualityReview.target_type == "ai_dialogue",
            QualityReview.target_id == session.id,
            QualityReview.reviewer_id == reviewer_id,
            QualityReview.deleted == 0,
        )
    )
    assessment_review = (
        db.scalar(
            select(QualityReview).where(
                QualityReview.target_type == "ai_assessment",
                QualityReview.target_id == assessment_target_id,
                QualityReview.reviewer_id == reviewer_id,
                QualityReview.deleted == 0,
            )
        )
        if assessment_target_id is not None
        else None
    )
    if dialogue_review is None and assessment_review is None:
        return None
    dialogue_scores, dialogue_comments = _review_scores(db, dialogue_review)
    assessment_scores, assessment_comments = _review_scores(db, assessment_review)
    latest_review = max(
        (item for item in (dialogue_review, assessment_review) if item is not None),
        key=lambda item: item.reviewed_at or item.update_time,
    )
    return QualityReviewResponse(
        task_id=str(task.id),
        reviewer_id=reviewer_id,
        dialogue_scores=dialogue_scores,
        assessment_scores=assessment_scores,
        dialogue_comments=dialogue_comments,
        assessment_comments=assessment_comments,
        comment=latest_review.review_comment or None,
        submitted_at=latest_review.reviewed_at,
    )
