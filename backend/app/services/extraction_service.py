"""字段抽取服务
作用：封装抽取字段查询逻辑。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

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
from app.models.patient_task import CareTask
from app.models.assessment_execution import AssessmentInstance
from app.services.assessment_progress_service import refresh_assessment_progress
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
    task = db.get(CareTask, session.task_id)

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
        logger.info(f"会话 {session_no} 暂无抽取结果，返回全部待填写字段")

    submission_ids = [s.id for s in submissions]

    # 3) 查询当前任务的全部量表字段，未识别字段也要返回给医护人工填写。
    target_questions = list(
        db.scalars(
            select(AssessmentQuestion)
            .join(
                AssessmentInstance,
                AssessmentInstance.scale_version_id
                == AssessmentQuestion.scale_version_id,
            )
            .where(
                AssessmentInstance.task_id == session.task_id,
                AssessmentInstance.deleted == 0,
                AssessmentQuestion.deleted == 0,
                AssessmentQuestion.derived.is_(False),
            )
            .order_by(AssessmentQuestion.scale_version_id, AssessmentQuestion.sort_no)
        ).all()
    )
    question_by_id = {question.id: question for question in target_questions}

    # 4) 查询答案及题目；当前 ORM 未声明 relationship，使用显式 JOIN。
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
    question_ids = list(question_by_id)
    option_definitions: dict[int, list[dict]] = defaultdict(list)
    if question_ids:
        for option in db.scalars(
            select(AssessmentOption)
            .where(
                AssessmentOption.question_id.in_(question_ids),
                AssessmentOption.deleted == 0,
            )
            .order_by(AssessmentOption.question_id, AssessmentOption.sort_no)
        ).all():
            option_definitions[option.question_id].append(
                {
                    "code": option.option_code,
                    "label": option.option_label,
                    "value": option.option_value,
                    "score": float(option.clinical_score)
                    if option.clinical_score is not None
                    else None,
                }
            )
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
                answer_type=answer.answer_type,
                options=option_definitions.get(answer.question_id, []),
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

    # 无效字段不写入 assessment_answer，仍然从提交快照恢复并展示给人工。
    for submission in submissions:
        for invalid in submission.invalid_answers or []:
            question_id = invalid.get("question_id")
            if question_id is None or any(
                field.question_id == int(question_id) and field.invalid
                for field in fields
            ):
                continue
            question = db.get(AssessmentQuestion, int(question_id))
            if question is None:
                continue
            fields.append(
                ExtractedFieldDto(
                    field_id=f"invalid-{submission.id}-{question.id}",
                    question_id=question.id,
                    question_code=question.question_code,
                    question_text=question.question_name,
                    answer_type=question.question_type,
                    options=option_definitions.get(question.id, []),
                    source_message_ids=None,
                    confidence=0,
                    corrected=False,
                    invalid=True,
                    invalid_reason=invalid.get("error"),
                    raw_answer=invalid.get("raw_answer"),
                )
            )

    recorded_ids = {field.question_id for field in fields}
    for question in target_questions:
        if question.id in recorded_ids:
            continue
        fields.append(
            ExtractedFieldDto(
                field_id=f"pending-{question.id}",
                question_id=question.id,
                question_code=question.question_code,
                question_text=question.question_name,
                answer_type=question.question_type,
                options=option_definitions.get(question.id, []),
                confidence=None,
                corrected=False,
            )
        )

    logger.info(f"会话 {session_no} 抽取字段: {len(fields)} 条")
    return ExtractedFieldsResponse(
        session_id=session_no,
        task_id=session.task_id,
        manual_intervention=bool(task and task.need_manual_intervention),
        intervention_reason=task.intervention_reason if task else None,
        fields=fields,
    )


def update_manual_field(
    db: Session,
    session_no: str,
    request,
    *,
    staff_id: int,
) -> ExtractedFieldsResponse:
    """保存医护人工字段，并按需结束人工介入状态。"""
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    task = db.get(CareTask, session.task_id)
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_001)
    question = db.get(AssessmentQuestion, request.question_id)
    if question is None or question.deleted:
        raise AppError(ErrorCode.ERR_COMMON_001, "字段不存在")
    if request.answer_type != question.question_type:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            f"字段类型不匹配，应使用 {question.question_type}",
        )
    instance = db.scalar(
        select(AssessmentInstance).where(
            AssessmentInstance.task_id == task.id,
            AssessmentInstance.scale_version_id == question.scale_version_id,
            AssessmentInstance.deleted == 0,
        )
    )
    if instance is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "字段不属于当前任务")
    submission = db.scalar(
        select(AssessmentSubmission)
        .where(
            AssessmentSubmission.assessment_instance_id == instance.id,
            AssessmentSubmission.submission_type == "ai_extraction",
            AssessmentSubmission.deleted == 0,
        )
        .order_by(AssessmentSubmission.id.desc())
    )
    if submission is None:
        from uuid import uuid4

        submission = AssessmentSubmission(
            submission_no=f"SUB-{uuid4().hex[:16].upper()}",
            assessment_instance_id=instance.id,
            submission_type="ai_extraction",
            submitter_type="nurse",
            submitter_id=staff_id,
            interaction_session_id=session.id,
            submission_status="in_progress",
            total_question_count=0,
            creator=f"staff:{staff_id}",
        )
        db.add(submission)
        db.flush()

    answer = db.scalar(
        select(AssessmentAnswer).where(
            AssessmentAnswer.submission_id == submission.id,
            AssessmentAnswer.question_id == request.question_id,
            AssessmentAnswer.deleted == 0,
        )
    )
    if answer is None:
        answer = AssessmentAnswer(
            submission_id=submission.id,
            question_id=request.question_id,
            answer_type=request.answer_type,
            value_source="nurse_corrected",
            creator=f"staff:{staff_id}",
        )
        db.add(answer)
    answer.answer_type = request.answer_type
    answer.answer_text = (
        request.answer_text if request.answer_type == "text" else None
    )
    answer.answer_number = (
        Decimal(str(request.answer_number))
        if request.answer_type == "number" and request.answer_number is not None
        else None
    )
    answer.answer_boolean = (
        request.answer_boolean
        if request.answer_type == "boolean"
        else None
    )
    answer.answer_date = (
        date.fromisoformat(request.answer_date)
        if request.answer_type == "date" and request.answer_date
        else None
    )
    answer.source_message_ids = ["manual"]
    answer.extraction_confidence = Decimal("1")
    answer.value_source = "nurse_corrected"
    answer.updator = f"staff:{staff_id}"
    db.flush()

    db.query(AssessmentAnswerOption).filter(
        AssessmentAnswerOption.assessment_answer_id == answer.id
    ).delete()
    if request.answer_type in {"single_choice", "multiple_choice"}:
        definitions = {
            option.option_code: option
            for option in db.scalars(
                select(AssessmentOption).where(
                    AssessmentOption.question_id == question.id,
                    AssessmentOption.option_code.in_(request.selected_option_codes),
                    AssessmentOption.deleted == 0,
                )
            ).all()
        }
        for code in request.selected_option_codes:
            option = definitions.get(code)
            if option is None:
                raise AppError(ErrorCode.ERR_COMMON_001, f"选项不存在: {code}")
            db.add(
                AssessmentAnswerOption(
                    assessment_answer_id=answer.id,
                    option_id=option.id,
                    option_code_snapshot=code,
                    option_label_snapshot=option.option_label,
                    clinical_score=option.clinical_score,
                    selected_flag=True,
                    creator=f"staff:{staff_id}",
                )
            )

    invalid = [
        item
        for item in (submission.invalid_answers or [])
        if int(item.get("question_id") or -1) != request.question_id
    ]
    submission.invalid_answers = invalid or None
    submission.updator = f"staff:{staff_id}"
    db.commit()
    refresh_assessment_progress(db, session_no)
    remaining_invalid = sum(
        len(item.invalid_answers or [])
        for item in db.scalars(
            select(AssessmentSubmission).where(
                AssessmentSubmission.interaction_session_id == session.id,
                AssessmentSubmission.submission_type == "ai_extraction",
                AssessmentSubmission.deleted == 0,
            )
        ).all()
    )
    if request.complete_manual and remaining_invalid == 0:
        task.need_manual_intervention = False
        task.intervention_reason = None
        task.updator = f"staff:{staff_id}"
        db.commit()
    # 人工修正先交给 Schedule Agent 评估后续任务影响；不立即触发 Dialog，
    # 下一次患者请求时由 Dialog Agent 动态读取约束。
    try:
        from app.celery_app.tasks import schedule_agent_worker
        from app.services.agent_dispatch_service import build_session_agent_payload

        patient_info, task_config = build_session_agent_payload(db, session)
        schedule_agent_worker.delay(
            session_no,
            {
                **task_config,
                "source_message_id": f"manual-field-{answer.id}",
                "source_event_id": None,
                "patient_info": patient_info,
                "manual_field_update": True,
            },
        )
    except Exception:
        logger.exception("人工字段后续 Schedule Agent 派发失败: session=%s", session_no)
    return get_extracted_fields(db, session_no)
