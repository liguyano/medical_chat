"""字段抽取服务
作用：封装抽取字段查询逻辑。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentSubmission,
)
from app.models.assessment_template import AssessmentQuestion
from app.models.interaction import InteractionSession
from app.schemas.extraction import ExtractedFieldDto, ExtractedFieldsResponse

logger = logging.getLogger(__name__)


def get_extracted_fields(db: Session, session_no: str) -> ExtractedFieldsResponse:
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

    # 3) 查询答案（带题目与选项）
    answers = list(
        db.execute(
            select(AssessmentAnswer)
            .options(
                joinedload(AssessmentAnswer.question),
                joinedload(AssessmentAnswer.selected_options),
            )
            .where(
                AssessmentAnswer.submission_id.in_(submission_ids),
                AssessmentAnswer.deleted == 0,
            )
            .order_by(AssessmentAnswer.id.asc())
        )
        .scalars()
        .all()
    )

    fields = []
    for ans in answers:
        if ans.question is None:
            continue

        # 选项编码列表
        selected_codes = None
        if ans.selected_options:
            selected_codes = [opt.option_code for opt in ans.selected_options]

        # source_message_ids 从 JSONB 字段读取
        source_ids = ans.source_message_ids if ans.source_message_ids else None

        fields.append(
            ExtractedFieldDto(
                field_id=f"ans-{ans.id}",
                question_id=ans.question_id,
                question_code=ans.question.question_code,
                question_text=ans.question.question_name,
                answer_text=ans.answer_text,
                answer_number=ans.answer_number,
                answer_boolean=ans.answer_boolean,
                selected_options=selected_codes,
                source_message_ids=source_ids,
                confidence=ans.extraction_confidence,
                corrected=False,  # 第一期无护士修正功能，默认 False
            )
        )

    logger.info(f"会话 {session_no} 抽取字段: {len(fields)} 条")
    return ExtractedFieldsResponse(session_id=session_no, fields=fields)
