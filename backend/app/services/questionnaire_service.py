"""传统问卷评估服务。
作用：加载任务量表快照、保存患者草稿、校验正式提交并生成规则计分结果。
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentInstance,
    AssessmentScore,
    AssessmentSubmission,
)
from app.models.assessment_template import (
    AssessmentOption,
    AssessmentQuestion,
    AssessmentRule,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSection,
)
from app.models.patient_task import CareTask
from app.schemas.questionnaire import (
    QuestionnaireAnswerDto,
    QuestionnaireAnswersRequest,
    QuestionnaireDto,
    QuestionnaireOptionDto,
    QuestionnaireQuestionDto,
    QuestionnaireScoreDto,
)
from app.services.assessment_progress_service import valid_assessment_answer_condition

_EMPTY_SUBMISSION_STATUSES = {"draft", "in_progress"}
_FINAL_SUBMISSION_STATUSES = {"submitted", "completed", "confirmed"}
logger = logging.getLogger(__name__)


def _resolve_task(db: Session, task_ref: str) -> CareTask:
    """按任务主键或业务编号加载任务。"""
    conditions = [CareTask.task_no == task_ref]
    if task_ref.isdigit():
        conditions.append(CareTask.id == int(task_ref))
    task = db.scalar(
        select(CareTask).where(or_(*conditions), CareTask.deleted == 0)
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    return task


def _assert_task_access(
    task: CareTask,
    *,
    patient_id: int | None = None,
    encounter_id: int | None = None,
    staff_id: int | None = None,
) -> None:
    """校验患者或责任护士对任务的访问边界。"""
    if patient_id is not None and (
        task.patient_id != patient_id or task.encounter_id != encounter_id
    ):
        raise AppError(ErrorCode.ERR_COMMON_002, "当前患者无权访问该问卷", 403)
    if staff_id is not None and (
        task.assigned_nurse_id is not None
        and task.assigned_nurse_id != staff_id
    ):
        raise AppError(ErrorCode.ERR_COMMON_002, "当前任务不属于登录医护人员", 403)


def _assert_traditional_task(task: CareTask) -> None:
    """保证问卷接口不会误操作 AI 对话任务。"""
    if task.collection_mode != "traditional_form":
        raise AppError(
            ErrorCode.ERR_COMMON_003,
            "当前任务不是传统问卷评估任务",
            http_status=409,
        )
    if task.task_status == "cancelled":
        raise AppError(ErrorCode.ERR_COMMON_003, "当前任务已取消", http_status=409)


def _assert_request_task_id(task: CareTask, request_task_id: str) -> None:
    """防止请求体任务编号与路径任务不一致。"""
    if request_task_id not in {str(task.id), task.task_no}:
        raise AppError(ErrorCode.ERR_COMMON_001, "请求任务编号与路径不一致")


def _load_instance_rows(
    db: Session,
    task_id: int,
) -> list[tuple[AssessmentInstance, AssessmentScale, AssessmentScaleVersion]]:
    """加载任务中的量表实例及其版本。"""
    rows = list(
        db.execute(
            select(AssessmentInstance, AssessmentScale, AssessmentScaleVersion)
            .join(AssessmentScale, AssessmentScale.id == AssessmentInstance.scale_id)
            .join(
                AssessmentScaleVersion,
                AssessmentScaleVersion.id == AssessmentInstance.scale_version_id,
            )
            .where(
                AssessmentInstance.task_id == task_id,
                AssessmentInstance.deleted == 0,
            )
            .order_by(AssessmentInstance.id.asc())
        ).all()
    )
    if not rows:
        raise AppError(ErrorCode.ERR_COMMON_001, "当前任务没有可填写的量表")
    return rows


def _load_question_rows(
    db: Session,
    instance_rows: list[tuple[AssessmentInstance, AssessmentScale, AssessmentScaleVersion]],
) -> list[tuple[AssessmentInstance, AssessmentScale, AssessmentScaleVersion, AssessmentQuestion, AssessmentSection | None]]:
    """加载题目和分组，题目顺序严格按量表版本定义。"""
    version_ids = [version.id for _, _, version in instance_rows]
    instance_by_version = {
        version.id: (instance, scale, version)
        for instance, scale, version in instance_rows
    }
    rows = list(
        db.execute(
            select(AssessmentQuestion, AssessmentSection)
            .outerjoin(
                AssessmentSection,
                AssessmentSection.id == AssessmentQuestion.section_id,
            )
            .where(
                AssessmentQuestion.scale_version_id.in_(version_ids),
                AssessmentQuestion.deleted == 0,
            )
            .order_by(
                AssessmentQuestion.scale_version_id.asc(),
                AssessmentQuestion.sort_no.asc(),
                AssessmentQuestion.id.asc(),
            )
        ).all()
    )
    return [
        (*instance_by_version[question.scale_version_id], question, section)
        for question, section in rows
    ]


def _load_options(
    db: Session,
    question_ids: list[int],
) -> dict[int, list[AssessmentOption]]:
    """批量读取题目选项。"""
    if not question_ids:
        return {}
    options = db.scalars(
        select(AssessmentOption)
        .where(
            AssessmentOption.question_id.in_(question_ids),
            AssessmentOption.deleted == 0,
        )
        .order_by(AssessmentOption.question_id.asc(), AssessmentOption.sort_no.asc())
    ).all()
    result: dict[int, list[AssessmentOption]] = {}
    for option in options:
        result.setdefault(option.question_id, []).append(option)
    return result


def _latest_submissions(
    db: Session,
    instance_ids: list[int],
) -> dict[int, AssessmentSubmission]:
    """读取每个量表实例最新的患者提交。"""
    if not instance_ids:
        return {}
    submissions = db.scalars(
        select(AssessmentSubmission)
        .where(
            AssessmentSubmission.assessment_instance_id.in_(instance_ids),
            AssessmentSubmission.submission_type == "patient_self",
            AssessmentSubmission.deleted == 0,
        )
        .order_by(AssessmentSubmission.id.asc())
    ).all()
    latest: dict[int, AssessmentSubmission] = {}
    for submission in submissions:
        latest[submission.assessment_instance_id] = submission
    return latest


def _latest_answers(
    db: Session,
    submission_ids: list[int],
) -> dict[int, AssessmentAnswer]:
    """读取当前患者提交中的题目答案。"""
    if not submission_ids:
        return {}
    answers = db.scalars(
        select(AssessmentAnswer)
        .where(
            AssessmentAnswer.submission_id.in_(submission_ids),
            AssessmentAnswer.deleted == 0,
        )
        .order_by(AssessmentAnswer.id.asc())
    ).all()
    return {answer.question_id: answer for answer in answers}


def _answer_options(
    db: Session,
    answer_ids: list[int],
) -> dict[int, list[AssessmentAnswerOption]]:
    """读取答案选项快照。"""
    if not answer_ids:
        return {}
    rows = db.scalars(
        select(AssessmentAnswerOption)
        .where(
            AssessmentAnswerOption.assessment_answer_id.in_(answer_ids),
            AssessmentAnswerOption.selected_flag.is_(True),
            AssessmentAnswerOption.deleted == 0,
        )
        .order_by(AssessmentAnswerOption.id.asc())
    ).all()
    result: dict[int, list[AssessmentAnswerOption]] = {}
    for row in rows:
        result.setdefault(row.assessment_answer_id, []).append(row)
    return result


def _to_float(value: Decimal | float | None) -> float | None:
    """将 Decimal 等数据库数值转为 JSON 可序列化浮点数。"""
    return float(value) if value is not None else None


def _display_value(
    answer: AssessmentAnswer | None,
    options: list[AssessmentAnswerOption],
) -> str | None:
    """构造用户可见答案。"""
    if answer is None:
        return None
    if options:
        return "、".join(option.option_label_snapshot for option in options)
    if answer.answer_text is not None:
        return answer.answer_text
    if answer.answer_number is not None:
        return str(answer.answer_number)
    if answer.answer_boolean is not None:
        return "是" if answer.answer_boolean else "否"
    if answer.answer_date is not None:
        return answer.answer_date.isoformat()
    return None


def _answer_dto(
    question: AssessmentQuestion,
    answer: AssessmentAnswer | None,
    options: list[AssessmentAnswerOption],
    option_values: dict[int, str],
) -> QuestionnaireAnswerDto:
    """将数据库答案转换为患者/医护端 DTO。"""
    return QuestionnaireAnswerDto(
        question_id=question.id,
        question_code=question.question_code,
        answer_type=question.question_type,
        answer_text=answer.answer_text if answer else None,
        answer_number=_to_float(answer.answer_number) if answer else None,
        answer_boolean=answer.answer_boolean if answer else None,
        answer_date=answer.answer_date.isoformat()
        if answer and answer.answer_date
        else None,
        selected_options=[option.option_code_snapshot for option in options],
        selected_option_labels=[option.option_label_snapshot for option in options],
        selected_option_values=[
            option_values.get(option.option_id, option.option_label_snapshot)
            for option in options
        ],
        display_value=_display_value(answer, options),
        clinical_score=_to_float(answer.clinical_score) if answer else None,
    )


def _question_dto(
    instance: AssessmentInstance,
    scale: AssessmentScale,
    version: AssessmentScaleVersion,
    question: AssessmentQuestion,
    section: AssessmentSection | None,
    options: dict[int, list[AssessmentOption]],
) -> QuestionnaireQuestionDto:
    """将量表题目转换为问卷页面所需 DTO。"""
    return QuestionnaireQuestionDto(
        id=question.id,
        scale_id=scale.id,
        scale_name=scale.scale_name,
        scale_version_id=version.id,
        section_id=section.id if section else None,
        section_name=section.section_name if section else None,
        question_code=question.question_code,
        question_text=question.patient_text or question.question_name,
        question_type=question.question_type,
        value_type=question.value_type,
        required=question.required,
        scored=question.scored,
        derived=question.derived,
        unit=question.unit,
        value_precision=question.value_precision,
        allow_other=question.allow_other,
        validation_rule=question.validation_rule,
        sort_no=question.sort_no,
        options=[
            QuestionnaireOptionDto(
                id=option.id,
                option_code=option.option_code,
                option_label=option.option_label,
                option_value=option.option_value,
                clinical_score=_to_float(option.clinical_score),
                requires_follow_up=option.requires_follow_up,
                extra_input_type=option.extra_input_type,
                extra_input_unit=option.extra_input_unit,
            )
            for option in options.get(question.id, [])
        ],
    )


def _status(
    task: CareTask,
    submissions: dict[int, AssessmentSubmission],
) -> str:
    """根据任务和患者提交状态生成问卷状态。"""
    if task.task_status == "completed":
        return "confirmed"
    if task.task_status == "pending_review":
        return "submitted"
    if task.task_status == "in_progress":
        if any(
            submission.submission_status in _FINAL_SUBMISSION_STATUSES
            for submission in submissions.values()
        ):
            return "returned"
        if any(
            submission.submission_status in _EMPTY_SUBMISSION_STATUSES
            and submission.answered_question_count > 0
            for submission in submissions.values()
        ):
            return "in_progress"
    return "not_started"


def _score_expression_matches(expression: str, total_score: Decimal) -> bool:
    """安全支持量表中常见的 total_score 比较表达式。"""
    clauses = re.split(r"\s+and\s+", expression.strip(), flags=re.IGNORECASE)
    for clause in clauses:
        match = re.fullmatch(
            r"\s*total_score\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*",
            clause,
        )
        if not match:
            return False
        threshold = Decimal(match.group(2))
        operator = match.group(1)
        if operator == ">=" and not total_score >= threshold:
            return False
        if operator == "<=" and not total_score <= threshold:
            return False
        if operator == "==" and total_score != threshold:
            return False
        if operator == ">" and not total_score > threshold:
            return False
        if operator == "<" and not total_score < threshold:
            return False
    return True


def _save_score(
    db: Session,
    *,
    submission: AssessmentSubmission,
    instance: AssessmentInstance,
    version: AssessmentScaleVersion,
    scale: AssessmentScale,
    answer_ids: list[int],
    creator: str,
) -> QuestionnaireScoreDto:
    """按选项临床分值汇总提交结果并保存规则解释。"""
    answers = db.scalars(
        select(AssessmentAnswer).where(
            AssessmentAnswer.id.in_(answer_ids),
            AssessmentAnswer.deleted == 0,
        )
    ).all()
    total = sum((answer.clinical_score or Decimal(0)) for answer in answers)
    rules = db.scalars(
        select(AssessmentRule)
        .where(
            AssessmentRule.scale_version_id == version.id,
            AssessmentRule.deleted == 0,
            AssessmentRule.status.in_(("启用", "active", "enabled")),
        )
        .order_by(AssessmentRule.priority.asc(), AssessmentRule.id.asc())
    ).all()
    result_summary: str | None = None
    risk_level: str | None = None
    for rule in rules:
        expression = (rule.condition_expression or {}).get("expression")
        if isinstance(expression, str) and _score_expression_matches(expression, total):
            payload = rule.result_payload or {}
            result_summary = str(payload.get("result") or payload.get("summary") or "") or None
            raw_risk = payload.get("risk_level")
            risk_level = str(raw_risk) if raw_risk is not None else None
            break

    submission.total_score = total
    submission.risk_level = risk_level
    submission.result_summary = result_summary
    db.execute(
        delete(AssessmentScore).where(
            AssessmentScore.submission_id == submission.id
        )
    )
    db.add(
        AssessmentScore(
            submission_id=submission.id,
            score_code="total_score",
            score_name="总分",
            score_type="total",
            score_value=total,
            risk_level=risk_level,
            interpretation=result_summary,
            calculation_detail={
                "scale_id": scale.id,
                "scale_version_id": version.id,
                "answer_ids": answer_ids,
            },
            creator=creator,
            updator=creator,
        )
    )
    return QuestionnaireScoreDto(
        scale_id=scale.id,
        scale_name=scale.scale_name,
        total_score=float(total),
        risk_level=risk_level,
        result_summary=result_summary,
    )


def _build_dto(db: Session, task: CareTask) -> QuestionnaireDto:
    """构建传统问卷完整 DTO。"""
    _assert_traditional_task(task)
    instance_rows = _load_instance_rows(db, task.id)
    question_rows = _load_question_rows(db, instance_rows)
    options = _load_options(db, [row[3].id for row in question_rows])
    option_values = {
        option.id: option.option_value
        for question_options in options.values()
        for option in question_options
    }
    submissions = _latest_submissions(db, [row[0].id for row in instance_rows])
    answers = _latest_answers(db, [submission.id for submission in submissions.values()])
    answer_options = _answer_options(db, list(answers.values()) and [answer.id for answer in answers.values()] or [])

    questions_dto = [
        _question_dto(instance, scale, version, question, section, options)
        for instance, scale, version, question, section in question_rows
    ]
    answers_dto = [
        _answer_dto(
            question,
            answers.get(question.id),
            answer_options.get(answers[question.id].id, [])
            if question.id in answers
            else [],
            option_values,
        )
        for _, _, _, question, _ in question_rows
        if question.id in answers
    ]
    scores: list[QuestionnaireScoreDto] = []
    for instance, scale, version in instance_rows:
        submission = submissions.get(instance.id)
        if submission is None or submission.total_score is None:
            continue
        scores.append(
            QuestionnaireScoreDto(
                scale_id=scale.id,
                scale_name=scale.scale_name,
                total_score=_to_float(submission.total_score),
                risk_level=submission.risk_level,
                result_summary=submission.result_summary,
            )
        )
    latest_submission = max(submissions.values(), key=lambda item: item.id, default=None)
    return QuestionnaireDto(
        task_id=task.id,
        task_no=task.task_no,
        collection_mode="traditional_form",
        status=_status(task, submissions),
        questions=questions_dto,
        answers=answers_dto,
        scores=scores,
        submitted_at=latest_submission.submitted_at if latest_submission else None,
        updated_at=latest_submission.update_time if latest_submission else task.update_time,
    )


def get_questionnaire(
    db: Session,
    task_ref: str,
    *,
    patient_id: int | None = None,
    encounter_id: int | None = None,
    staff_id: int | None = None,
) -> QuestionnaireDto:
    """查询传统问卷题目和当前提交。"""
    task = _resolve_task(db, task_ref)
    _assert_task_access(
        task,
        patient_id=patient_id,
        encounter_id=encounter_id,
        staff_id=staff_id,
    )
    return _build_dto(db, task)


def _question_maps(
    question_rows: list[
        tuple[
            AssessmentInstance,
            AssessmentScale,
            AssessmentScaleVersion,
            AssessmentQuestion,
            AssessmentSection | None,
        ]
    ],
) -> tuple[dict[str, tuple[AssessmentInstance, AssessmentQuestion]], dict[int, tuple[AssessmentInstance, AssessmentQuestion]]]:
    """构造题目编码和 ID 到实例/题目的索引。"""
    by_code: dict[str, tuple[AssessmentInstance, AssessmentQuestion]] = {}
    by_id: dict[int, tuple[AssessmentInstance, AssessmentQuestion]] = {}
    for instance, _, _, question, _ in question_rows:
        by_code[question.question_code] = (instance, question)
        by_id[question.id] = (instance, question)
    return by_code, by_id


def _decimal_value(value: Any, question: AssessmentQuestion) -> Decimal:
    """解析数字答案并执行精度/范围校验。"""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            f"题目“{question.question_name}”需要填写有效数字",
        ) from exc
    rule = question.validation_rule or {}
    min_value = rule.get("min", rule.get("minimum"))
    max_value = rule.get("max", rule.get("maximum"))
    if min_value is not None and number < Decimal(str(min_value)):
        raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”数值过小")
    if max_value is not None and number > Decimal(str(max_value)):
        raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”数值过大")
    precision = question.value_precision
    if precision is not None and number.as_tuple().exponent < -int(precision):
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            f"题目“{question.question_name}”最多保留 {precision} 位小数",
        )
    return number


def _parse_value(
    question: AssessmentQuestion,
    raw_value: Any,
    option_map: dict[str, AssessmentOption],
) -> dict[str, Any] | None:
    """按量表题型归一化患者答案。"""
    if raw_value is None or raw_value == "" or raw_value == []:
        return None
    question_type = question.question_type
    if question_type in {"single_choice", "grouped_choice"}:
        if not isinstance(raw_value, str) or raw_value not in option_map:
            raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”选项无效")
        option = option_map[raw_value]
        return {
            "answer_type": "single_choice",
            "selected_options": [option],
            "clinical_score": option.clinical_score,
        }
    if question_type == "multiple_choice":
        if not isinstance(raw_value, list) or not all(
            isinstance(item, str) and item in option_map for item in raw_value
        ) or len(set(raw_value)) != len(raw_value):
            raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”选项无效")
        selected = [option_map[item] for item in raw_value]
        return {
            "answer_type": "multiple_choice",
            "selected_options": selected,
            "clinical_score": sum(
                (option.clinical_score or Decimal(0)) for option in selected
            ),
        }
    if question_type == "number":
        return {
            "answer_type": "number",
            "answer_number": _decimal_value(raw_value, question),
        }
    if question_type == "boolean":
        if isinstance(raw_value, bool):
            value = raw_value
        elif isinstance(raw_value, str) and raw_value in {"true", "是", "1"}:
            value = True
        elif isinstance(raw_value, str) and raw_value in {"false", "否", "0"}:
            value = False
        elif isinstance(raw_value, int) and raw_value in {0, 1}:
            value = bool(raw_value)
        else:
            raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”需要选择是或否")
        return {"answer_type": "boolean", "answer_boolean": value}
    if question_type == "date":
        try:
            parsed = date.fromisoformat(str(raw_value))
        except ValueError as exc:
            raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”日期格式无效") from exc
        return {"answer_type": "date", "answer_date": parsed}
    if not isinstance(raw_value, str):
        raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”需要填写文本")
    rule = question.validation_rule or {}
    max_length = rule.get("max_length", rule.get("maxLength"))
    if max_length is not None and len(raw_value) > int(max_length):
        raise AppError(ErrorCode.ERR_COMMON_001, f"题目“{question.question_name}”内容过长")
    return {"answer_type": "text", "answer_text": raw_value}


def _upsert_answer(
    db: Session,
    *,
    submission: AssessmentSubmission,
    question: AssessmentQuestion,
    parsed: dict[str, Any] | None,
    option_map: dict[str, AssessmentOption],
    actor: str,
) -> None:
    """将归一化答案写入一条提交。"""
    answer = db.scalar(
        select(AssessmentAnswer).where(
            AssessmentAnswer.submission_id == submission.id,
            AssessmentAnswer.question_id == question.id,
            AssessmentAnswer.deleted == 0,
        )
    )
    if parsed is None:
        if answer is not None:
            # 先显式删除选项快照，避免数据库未启用级联时遗留孤儿快照。
            db.execute(
                delete(AssessmentAnswerOption).where(
                    AssessmentAnswerOption.assessment_answer_id == answer.id
                )
            )
            db.delete(answer)
        return
    if answer is None:
        answer = AssessmentAnswer(
            submission_id=submission.id,
            question_id=question.id,
            answer_type=parsed["answer_type"],
            value_source="patient_input",
            creator=actor,
        )
        db.add(answer)
        db.flush()
    answer.answer_type = parsed["answer_type"]
    answer.answer_text = parsed.get("answer_text")
    answer.answer_number = parsed.get("answer_number")
    answer.answer_boolean = parsed.get("answer_boolean")
    answer.answer_date = parsed.get("answer_date")
    answer.clinical_score = parsed.get("clinical_score")
    answer.value_source = "patient_input"
    answer.extraction_confidence = None
    answer.source_message_ids = None
    answer.updator = actor
    db.execute(
        delete(AssessmentAnswerOption).where(
            AssessmentAnswerOption.assessment_answer_id == answer.id
        )
    )
    for option in parsed.get("selected_options", []):
        db.add(
            AssessmentAnswerOption(
                assessment_answer_id=answer.id,
                option_id=option.id,
                option_code_snapshot=option.option_code,
                option_label_snapshot=option.option_label,
                clinical_score=option.clinical_score,
                selected_flag=True,
                creator=actor,
                updator=actor,
            )
        )


def _submission_for_instance(
    db: Session,
    *,
    instance: AssessmentInstance,
    task: CareTask,
    total_questions: int,
    actor: str,
) -> AssessmentSubmission:
    """获取可编辑患者提交，退回任务创建新的提交版本。"""
    # 锁住实例行，避免患者重复点击或并发重试在“尚无提交”时创建两条草稿。
    db.execute(
        select(AssessmentInstance.id)
        .where(AssessmentInstance.id == instance.id)
        .with_for_update()
    )
    latest = db.scalar(
        select(AssessmentSubmission)
        .where(
            AssessmentSubmission.assessment_instance_id == instance.id,
            AssessmentSubmission.submission_type == "patient_self",
            AssessmentSubmission.deleted == 0,
        )
        .order_by(AssessmentSubmission.id.desc())
        .with_for_update()
    )
    if latest is not None and latest.submission_status in _EMPTY_SUBMISSION_STATUSES:
        return latest
    if latest is not None and task.task_status in {"pending_review", "completed"}:
        return latest
    submission = AssessmentSubmission(
        submission_no=f"SUB-{uuid.uuid4().hex[:16].upper()}",
        assessment_instance_id=instance.id,
        submission_type="patient_self",
        submitter_type="patient",
        submitter_id=task.patient_id,
        submission_status="in_progress",
        total_question_count=total_questions,
        answered_question_count=0,
        creator=actor,
        updator=actor,
    )
    db.add(submission)
    db.flush()
    return submission


def _save_answers(
    db: Session,
    task: CareTask,
    request: QuestionnaireAnswersRequest,
    *,
    actor: str,
) -> tuple[list[tuple[AssessmentInstance, AssessmentScale, AssessmentScaleVersion, AssessmentSubmission]], list[int]]:
    """保存草稿答案并返回提交实例与缺失题目。"""
    instance_rows = _load_instance_rows(db, task.id)
    question_rows = _load_question_rows(db, instance_rows)
    by_code, by_id = _question_maps(question_rows)
    options = _load_options(db, [row[3].id for row in question_rows])
    submissions_by_instance: dict[int, AssessmentSubmission] = {}
    for instance, _, version in instance_rows:
        total_questions = sum(
            int(question.required and not question.derived)
            for _, _, row_version, question, _ in question_rows
            if row_version.id == version.id
        )
        submissions_by_instance[instance.id] = _submission_for_instance(
            db,
            instance=instance,
            task=task,
            total_questions=total_questions,
            actor=actor,
        )

    for raw_key, raw_value in request.answers.items():
        resolved = by_code.get(raw_key)
        if resolved is None and raw_key.isdigit():
            resolved = by_id.get(int(raw_key))
        if resolved is None:
            raise AppError(ErrorCode.ERR_COMMON_001, f"题目不存在: {raw_key}")
        instance, question = resolved
        if question.derived:
            raise AppError(
                ErrorCode.ERR_COMMON_001,
                f"题目“{question.question_name}”由系统计算，不能手工填写",
            )
        option_map = {
            option.option_code: option for option in options.get(question.id, [])
        }
        parsed = _parse_value(question, raw_value, option_map)
        _upsert_answer(
            db,
            submission=submissions_by_instance[instance.id],
            question=question,
            parsed=parsed,
            option_map=option_map,
            actor=actor,
        )

    missing: list[int] = []
    for instance, _, version in instance_rows:
        submission = submissions_by_instance[instance.id]
        required_ids = [
            question.id
            for _, _, row_version, question, _ in question_rows
            if row_version.id == version.id and question.required and not question.derived
        ]
        answered_ids = set(
            db.scalars(
                select(AssessmentAnswer.question_id).where(
                    AssessmentAnswer.submission_id == submission.id,
                    AssessmentAnswer.deleted == 0,
                    valid_assessment_answer_condition(),
                )
            ).all()
        )
        missing.extend(question_id for question_id in required_ids if question_id not in answered_ids)
        submission.total_question_count = len(required_ids)
        submission.answered_question_count = len(answered_ids.intersection(required_ids))
        submission.updator = actor

    return [
        (instance, scale, version, submissions_by_instance[instance.id])
        for instance, scale, version in instance_rows
    ], missing


def save_draft(
    db: Session,
    task_ref: str,
    request: QuestionnaireAnswersRequest,
    *,
    patient_id: int,
    encounter_id: int,
) -> QuestionnaireDto:
    """保存患者问卷草稿。"""
    task = _resolve_task(db, task_ref)
    _assert_task_access(task, patient_id=patient_id, encounter_id=encounter_id)
    _assert_traditional_task(task)
    _assert_request_task_id(task, request.task_id)
    if task.task_status in {"pending_review", "completed"}:
        raise AppError(ErrorCode.ERR_COMMON_003, "问卷已提交，当前不可修改", http_status=409)
    try:
        _save_answers(db, task, request, actor=f"patient:{patient_id}")
        now = datetime.now(UTC)
        if task.started_at is None:
            task.started_at = now
        task.task_status = "in_progress"
        task.updator = f"patient:{patient_id}"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _build_dto(db, task)


def submit_questionnaire(
    db: Session,
    task_ref: str,
    request: QuestionnaireAnswersRequest,
    *,
    patient_id: int,
    encounter_id: int,
) -> QuestionnaireDto:
    """校验并正式提交患者传统问卷。"""
    task = _resolve_task(db, task_ref)
    _assert_task_access(task, patient_id=patient_id, encounter_id=encounter_id)
    _assert_traditional_task(task)
    _assert_request_task_id(task, request.task_id)
    if task.task_status in {"pending_review", "completed"}:
        return _build_dto(db, task)
    try:
        submissions, missing = _save_answers(
            db,
            task,
            request,
            actor=f"patient:{patient_id}",
        )
        if missing:
            db.rollback()
            raise AppError(
                ErrorCode.ERR_COMMON_001,
                "请完成全部必填题后再提交，未完成题目: "
                + ",".join(str(item) for item in missing),
            )
        now = datetime.now(UTC)
        for instance, scale, version, submission in submissions:
            answer_ids = list(
                db.scalars(
                    select(AssessmentAnswer.id).where(
                        AssessmentAnswer.submission_id == submission.id,
                        AssessmentAnswer.deleted == 0,
                    )
                ).all()
            )
            _save_score(
                db,
                submission=submission,
                instance=instance,
                version=version,
                scale=scale,
                answer_ids=answer_ids,
                creator=f"patient:{patient_id}",
            )
            submission.submission_status = "submitted"
            submission.submitted_at = now
            submission.updator = f"patient:{patient_id}"
            instance.instance_status = "pending_nurse_review"
            instance.assessed_at = now
            instance.updator = "questionnaire"
        task.task_status = "pending_review"
        task.completed_at = now
        task.updator = f"patient:{patient_id}"
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        from app.celery_app.tasks import nursing_plan_worker

        nursing_plan_worker.delay(task.id, False)
    except Exception:
        # 问卷提交已落库，护理计划异步派发失败不影响患者提交结果。
        logger.exception("传统问卷护理计划任务派发失败: task=%s", task.id)
    return _build_dto(db, task)
