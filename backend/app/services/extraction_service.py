"""字段抽取服务
作用：封装抽取字段查询逻辑。
"""
from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentSubmission,
)
from app.models.assessment_template import AssessmentOption, AssessmentQuestion
from app.models.interaction import InteractionSession
from app.schemas.extraction import ExtractedFieldDto, ExtractedFieldsResponse

logger = logging.getLogger(__name__)


def _build_display_value(
    *,
    answer_text: str | None,
    answer_number: object | None,
    answer_boolean: bool | None,
    selected_labels: list[str] | None,
) -> str | None:
    """构造结构化答案的用户可见值，避免暴露 option code。"""
    if selected_labels:
        return "、".join(selected_labels)
    if answer_text is not None:
        return str(answer_text)
    if answer_number is not None:
        return str(answer_number)
    if answer_boolean is not None:
        return "是" if answer_boolean else "否"
    return None


def get_extracted_fields(
    db: Session,
    session_no: str,
    *,
    patient_id: int | None = None,
) -> ExtractedFieldsResponse:
    """获取会话抽取字段
    作用：查询指定会话的 AI 抽取结果（submission_type="ai_extraction"），
          返回字段列表供前端展示。
    Args:
        - db: 数据库会话
        - session_no: 会话编号
    Return:
        - ExtractedFieldsResponse: 包含会话编号与字段列表
    """
    # 1) 校验会话存在
    session = db.execute(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    ).scalar_one_or_none()
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    if patient_id is not None and session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权访问该会话")

    # 2) 查询该会话的 AI 抽取提交记录
    submissions = list(
        db.scalars(
            select(AssessmentSubmission).where(
                AssessmentSubmission.interaction_session_id == session.id,
                AssessmentSubmission.submission_type == "ai_extraction",
                AssessmentSubmission.deleted == 0,
            )
        ).all()
    )

    if not submissions:
        logger.info(f"会话 {session_no} 暂无抽取结果")
        return ExtractedFieldsResponse(session_id=session_no, fields=[])

    submission_ids = [s.id for s in submissions]

    # 3) 查询答案及题目；当前 ORM 未声明 relationship，使用显式 JOIN。
    answer_rows = list(
        db.execute(
            select(AssessmentAnswer, AssessmentQuestion)
            .join(
                AssessmentQuestion,
                AssessmentQuestion.id == AssessmentAnswer.question_id,
            )
            .where(
                AssessmentAnswer.submission_id.in_(submission_ids),
                AssessmentAnswer.deleted == 0,
                AssessmentQuestion.deleted == 0,
            )
            .order_by(AssessmentAnswer.id.asc())
        )
        .all()
    )

    answer_ids = [answer.id for answer, _ in answer_rows]
    option_codes_by_answer: dict[int, list[str]] = defaultdict(list)
    option_labels_by_answer: dict[int, list[str]] = defaultdict(list)
    option_values_by_answer: dict[int, list[str]] = defaultdict(list)
    if answer_ids:
        option_rows = db.execute(
            select(
                AssessmentAnswerOption.assessment_answer_id,
                AssessmentAnswerOption.option_code_snapshot,
                AssessmentAnswerOption.option_label_snapshot,
                AssessmentOption.option_value,
            )
            .outerjoin(
                AssessmentOption,
                AssessmentOption.id == AssessmentAnswerOption.option_id,
            )
            .where(
                AssessmentAnswerOption.assessment_answer_id.in_(answer_ids),
                AssessmentAnswerOption.selected_flag.is_(True),
                AssessmentAnswerOption.deleted == 0,
            )
            .order_by(AssessmentAnswerOption.id.asc())
        ).all()
        for answer_id, option_code, option_label, option_value in option_rows:
            option_codes_by_answer[answer_id].append(option_code)
            option_labels_by_answer[answer_id].append(option_label)
            option_values_by_answer[answer_id].append(
                str(option_value) if option_value is not None else option_label
            )

    fields = []
    for answer, question in answer_rows:
        selected_codes = option_codes_by_answer.get(answer.id) or None
        selected_labels = option_labels_by_answer.get(answer.id) or None
        selected_values = option_values_by_answer.get(answer.id) or None
        display_value = _build_display_value(
            answer_text=answer.answer_text,
            answer_number=answer.answer_number,
            answer_boolean=answer.answer_boolean,
            selected_labels=selected_labels,
        )
        source_ids = (
            [str(message_id) for message_id in answer.source_message_ids]
            if answer.source_message_ids
            else None
        )

        fields.append(
            ExtractedFieldDto(
                field_id=f"ans-{answer.id}",
                question_id=answer.question_id,
                question_code=question.question_code,
                question_text=question.question_name,
                answer_text=answer.answer_text,
                answer_number=answer.answer_number,
                answer_boolean=answer.answer_boolean,
                selected_options=selected_codes,
                selected_option_labels=selected_labels,
                selected_option_values=selected_values,
                display_value=display_value,
                source_message_ids=source_ids,
                confidence=answer.extraction_confidence,
                corrected=False,  # 第一期无护士修正功能，默认 False
            )
        )

    logger.info(f"会话 {session_no} 抽取字段: {len(fields)} 条")
    return ExtractedFieldsResponse(session_id=session_no, fields=fields)
