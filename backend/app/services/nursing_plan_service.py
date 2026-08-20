"""患者画像与护理计划服务
作用：聚合评估证据，调用真实模型生成 AI 草案，并支持护士编辑和确认。
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from medagent.providers import create_chat_model
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentInstance,
    AssessmentScore,
    AssessmentSubmission,
)
from app.models.assessment_template import AssessmentQuestion, AssessmentScale
from app.models.interaction import InteractionSession
from app.models.nursing_plan import (
    NursingPlan,
    NursingPlanItem,
    PatientProfileSnapshot,
)
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.schemas.nursing_plan import (
    AiNursingPlanOutput,
    NursingPlanDto,
    NursingPlanItemDto,
    NursingPlanUpdateRequest,
    PatientProfileDto,
)

logger = logging.getLogger(__name__)

_SUBMISSION_PRIORITY = {
    "final_confirmed": 30,
    "最终确认": 30,
    "nurse_independent": 20,
    "护士独立": 20,
    "ai_extracted": 10,
    "ai_extraction": 10,
    "AI抽取": 10,
}


def _business_no(prefix: str) -> str:
    """生成患者画像或护理计划业务编号。"""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _calculate_age(birthday: date | None) -> int | None:
    """计算患者当前周岁。"""
    if birthday is None:
        return None
    today = datetime.now(UTC).date()
    return today.year - birthday.year - (
        (today.month, today.day) < (birthday.month, birthday.day)
    )


def _load_task(db: Session, task_ref: str | int) -> CareTask:
    """按主键或任务编号加载护理任务。"""
    value = str(task_ref)
    conditions = [CareTask.task_no == value]
    if value.isdigit():
        conditions.append(CareTask.id == int(value))
    task = db.scalar(
        select(CareTask).where(
            or_(*conditions),
            CareTask.deleted == 0,
        )
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    return task


def _assert_task_owner(task: CareTask, staff_id: int) -> None:
    """限制护理计划由任务责任护士访问。"""
    if task.assigned_nurse_id is not None and task.assigned_nurse_id != staff_id:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            "当前任务不属于登录医护人员",
            http_status=403,
        )


def _select_source_submission(
    db: Session,
    instance_id: int,
) -> AssessmentSubmission | None:
    """按最终确认、护士独立、AI 抽取顺序选择一份来源提交。"""
    rows = list(
        db.scalars(
            select(AssessmentSubmission)
            .where(
                AssessmentSubmission.assessment_instance_id == instance_id,
                AssessmentSubmission.deleted == 0,
            )
            .order_by(AssessmentSubmission.id.desc())
        ).all()
    )
    candidates = [
        row for row in rows if row.submission_type in _SUBMISSION_PRIORITY
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (
            _SUBMISSION_PRIORITY[row.submission_type],
            row.id,
        ),
    )


def _scalar_value(value: Any) -> Any:
    """把 Decimal、日期时间等数据库值转换为 JSON 可序列化值。"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _answer_value(
    answer: AssessmentAnswer,
    option_labels: list[str],
) -> str | float | bool | None:
    """生成模型可读的结构化答案值。"""
    if option_labels:
        return "、".join(option_labels)
    for value in (
        answer.answer_text,
        answer.answer_number,
        answer.answer_boolean,
        answer.answer_date,
        answer.answer_time,
        answer.answer_datetime,
    ):
        if value is not None:
            return _scalar_value(value)
    return None


def build_generation_source(
    db: Session,
    task: CareTask,
) -> tuple[dict[str, Any], list[int]]:
    """聚合任务下量表、答案、得分和会话摘要作为模型证据。"""
    patient = db.get(Patient, task.patient_id)
    encounter = db.get(PatientEncounter, task.encounter_id)
    if patient is None or encounter is None:
        raise AppError(ErrorCode.ERR_TASK_003, "任务关联患者或住院记录不存在")

    instance_rows = list(
        db.execute(
            select(AssessmentInstance, AssessmentScale)
            .join(
                AssessmentScale,
                AssessmentScale.id == AssessmentInstance.scale_id,
            )
            .where(
                AssessmentInstance.task_id == task.id,
                AssessmentInstance.deleted == 0,
                AssessmentScale.deleted == 0,
            )
            .order_by(AssessmentInstance.id.asc())
        ).all()
    )
    source_submissions: list[AssessmentSubmission] = []
    scale_by_instance: dict[int, AssessmentScale] = {}
    for instance, scale in instance_rows:
        submission = _select_source_submission(db, instance.id)
        if submission is not None:
            source_submissions.append(submission)
            scale_by_instance[instance.id] = scale
    if not source_submissions:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            "当前任务尚无可用于生成护理计划的评估结果",
        )

    submission_ids = [item.id for item in source_submissions]
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
            .order_by(AssessmentAnswer.submission_id, AssessmentAnswer.id)
        ).all()
    )
    answer_ids = [answer.id for answer, _ in answer_rows]
    labels_by_answer: dict[int, list[str]] = defaultdict(list)
    if answer_ids:
        for answer_id, label in db.execute(
            select(
                AssessmentAnswerOption.assessment_answer_id,
                AssessmentAnswerOption.option_label_snapshot,
            )
            .where(
                AssessmentAnswerOption.assessment_answer_id.in_(answer_ids),
                AssessmentAnswerOption.selected_flag.is_(True),
                AssessmentAnswerOption.deleted == 0,
            )
            .order_by(AssessmentAnswerOption.id.asc())
        ):
            labels_by_answer[answer_id].append(label)

    answers_by_submission: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for answer, question in answer_rows:
        value = _answer_value(answer, labels_by_answer[answer.id])
        if value is None:
            continue
        answers_by_submission[answer.submission_id].append(
            {
                "answer_id": answer.id,
                "question_code": question.question_code,
                "question": question.question_name,
                "value": value,
                "clinical_score": _scalar_value(answer.clinical_score),
                "abnormal": answer.abnormal_flag,
                "risk_tags": answer.risk_tags or [],
                "confidence": _scalar_value(answer.extraction_confidence),
            }
        )

    score_rows = list(
        db.scalars(
            select(AssessmentScore)
            .where(
                AssessmentScore.submission_id.in_(submission_ids),
                AssessmentScore.deleted == 0,
            )
            .order_by(AssessmentScore.submission_id, AssessmentScore.id)
        ).all()
    )
    scores_by_submission: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for score in score_rows:
        scores_by_submission[score.submission_id].append(
            {
                "score_id": score.id,
                "score_code": score.score_code,
                "score_name": score.score_name,
                "score_value": _scalar_value(score.score_value),
                "max_score": _scalar_value(score.max_score),
                "risk_level": score.risk_level,
                "interpretation": score.interpretation,
            }
        )

    session = db.scalar(
        select(InteractionSession)
        .where(
            InteractionSession.task_id == task.id,
            InteractionSession.deleted == 0,
        )
        .order_by(InteractionSession.id.desc())
    )
    assessments = []
    for submission in source_submissions:
        scale = scale_by_instance[submission.assessment_instance_id]
        assessments.append(
            {
                "scale_code": scale.scale_code,
                "scale_name": scale.scale_name,
                "submission_id": submission.id,
                "submission_type": submission.submission_type,
                "result_summary": submission.result_summary,
                "risk_level": submission.risk_level,
                "answers": answers_by_submission[submission.id],
                "scores": scores_by_submission[submission.id],
            }
        )
    source = {
        "task": {
            "task_id": task.id,
            "task_no": task.task_no,
            "collection_mode": task.collection_mode,
            "task_status": task.task_status,
        },
        "patient": {
            "name": patient.patient_name,
            "sex": patient.sex,
            "age": _calculate_age(patient.birthday),
            "department": encounter.department_name,
            "ward": encounter.ward_name,
            "bed_no": encounter.bed_no,
            "diagnosis": encounter.diagnosis_snapshot,
        },
        "dialogue_summary": session.ai_summary if session else None,
        "assessments": assessments,
    }
    return source, submission_ids


def _message_text(content: Any) -> str:
    """提取 LangChain 消息中的文本内容。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks: list[str] = []
        for item in content:
            if isinstance(item, str):
                blocks.append(item)
            elif isinstance(item, dict) and item.get("text"):
                blocks.append(str(item["text"]))
        return "\n".join(blocks)
    return str(content or "")


def _parse_model_output(content: Any) -> AiNursingPlanOutput:
    """从模型回复中提取并校验 JSON。"""
    text = _message_text(content).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return AiNursingPlanOutput.model_validate_json(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return AiNursingPlanOutput.model_validate_json(text[start : end + 1])


async def generate_ai_output(
    source: dict[str, Any],
    *,
    model: BaseChatModel | None = None,
) -> tuple[AiNursingPlanOutput, str]:
    """调用真实语言模型生成患者画像与护理计划。"""
    model_name = "injected-test-model"
    if model is None:
        config = get_app_config()
        model_config = (
            config.get_agent_model_config("nursing_plan_agent")
            or config.get_agent_model_config("extraction_agent")
        )
        if model_config is None:
            raise RuntimeError("未配置护理计划或抽取语言模型")
        # 结构化 JSON 链路必须关闭思考模式，避免推理 token 截断结果。
        model_config = model_config.model_copy(update={"enable_thinking": False})
        model_name = model_config.name
        model = create_chat_model(model_config)

    schema = AiNursingPlanOutput.model_json_schema()
    messages = [
        SystemMessage(
            content=(
                "你是住院护理计划辅助生成器。只能根据提供的评估证据生成差异化护理建议，"
                "不得补造诊断、药物或检查结果。输出必须是单个 JSON 对象，不要 Markdown。"
                "护理措施是护士待确认建议，不得描述为已经执行。风险不明确时使用 unknown。"
            )
        ),
        HumanMessage(
            content=(
                "请生成患者画像、风险摘要、宣教重点、交接班重点和结构化护理计划项。\n"
                f"输出 JSON Schema：{json.dumps(schema, ensure_ascii=False)}\n"
                f"评估证据：{json.dumps(source, ensure_ascii=False, default=str)}"
            )
        ),
    ]
    response = await model.ainvoke(messages)
    return _parse_model_output(response.content), model_name


def _latest_plan_for_task(
    db: Session,
    task: CareTask,
) -> tuple[NursingPlan, PatientProfileSnapshot] | None:
    """查询指定任务最近一次未结束的护理计划。"""
    return db.execute(
        select(NursingPlan, PatientProfileSnapshot)
        .join(
            PatientProfileSnapshot,
            PatientProfileSnapshot.id == NursingPlan.profile_snapshot_id,
        )
        .where(
            NursingPlan.patient_id == task.patient_id,
            NursingPlan.encounter_id == task.encounter_id,
            NursingPlan.deleted == 0,
            NursingPlan.plan_status != "ended",
            PatientProfileSnapshot.deleted == 0,
            PatientProfileSnapshot.profile_detail["task_id"].astext
            == str(task.id),
        )
        .order_by(NursingPlan.id.desc())
    ).first()


def _to_dto(
    db: Session,
    plan: NursingPlan,
    profile: PatientProfileSnapshot,
) -> NursingPlanDto:
    """转换护理计划组合 DTO。"""
    items = list(
        db.scalars(
            select(NursingPlanItem)
            .where(
                NursingPlanItem.nursing_plan_id == plan.id,
                NursingPlanItem.deleted == 0,
            )
            .order_by(
                NursingPlanItem.priority.desc(),
                NursingPlanItem.id.asc(),
            )
        ).all()
    )
    return NursingPlanDto(
        id=plan.id,
        task_id=int(profile.profile_detail.get("task_id")),
        plan_no=plan.plan_no,
        plan_status=plan.plan_status,
        risk_summary=plan.risk_summary,
        education_summary=plan.education_summary,
        handover_summary=plan.handover_summary,
        generated_by=plan.generated_by,
        confirmed_by=plan.confirmed_by,
        confirmed_at=(
            plan.confirmed_at.isoformat() if plan.confirmed_at else None
        ),
        profile=PatientProfileDto(
            id=profile.id,
            profile_no=profile.profile_no,
            source_submission_ids=[
                int(item) for item in profile.source_submission_ids
            ],
            cooperation_level=profile.cooperation_level,
            cognition_level=profile.cognition_level,
            self_care_level=profile.self_care_level,
            fall_risk_level=profile.fall_risk_level,
            pressure_risk_level=profile.pressure_risk_level,
            nutrition_risk_level=profile.nutrition_risk_level,
            communication_level=profile.communication_level,
            education_need_level=profile.education_need_level,
            profile_detail=profile.profile_detail,
            generated_by=profile.generated_by,
            generated_at=profile.generated_at.isoformat(),
        ),
        items=[
            NursingPlanItemDto(
                id=item.id,
                item_type=item.item_type,
                item_code=item.item_code,
                item_content=item.item_content,
                source_type=item.source_type,
                source_id=item.source_id,
                priority=item.priority,
                nurse_action=item.nurse_action,
                nurse_comment=item.nurse_comment,
            )
            for item in items
        ],
    )


def get_nursing_plan(
    db: Session,
    task_ref: str | int,
    *,
    staff_id: int,
) -> NursingPlanDto | None:
    """查询任务最近一次患者画像和护理计划。"""
    task = _load_task(db, task_ref)
    _assert_task_owner(task, staff_id)
    row = _latest_plan_for_task(db, task)
    return _to_dto(db, *row) if row else None


async def generate_nursing_plan(
    db: Session,
    task_ref: str | int,
    *,
    staff_id: int | None = None,
    force: bool = False,
    model: BaseChatModel | None = None,
) -> NursingPlanDto:
    """生成患者画像和 AI 护理计划草案。"""
    task = _load_task(db, task_ref)
    if staff_id is not None:
        _assert_task_owner(task, staff_id)
    if task.task_status not in {"pending_review", "completed"}:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            "评估尚未完成，暂不能生成护理计划",
        )
    existing = _latest_plan_for_task(db, task)
    if existing and not force:
        return _to_dto(db, *existing)

    source, submission_ids = build_generation_source(db, task)
    output, model_name = await generate_ai_output(source, model=model)
    now = datetime.now(UTC)
    try:
        if existing:
            existing[0].plan_status = "ended"
            existing[0].updator = "nursing_plan_regeneration"
        profile = PatientProfileSnapshot(
            profile_no=_business_no("PROFILE"),
            patient_id=task.patient_id,
            encounter_id=task.encounter_id,
            source_submission_ids=submission_ids,
            cooperation_level=output.profile.cooperation_level,
            cognition_level=output.profile.cognition_level,
            self_care_level=output.profile.self_care_level,
            fall_risk_level=output.profile.fall_risk_level,
            pressure_risk_level=output.profile.pressure_risk_level,
            nutrition_risk_level=output.profile.nutrition_risk_level,
            communication_level=output.profile.communication_level,
            education_need_level=output.profile.education_need_level,
            profile_detail={
                "task_id": task.id,
                "summary": output.profile.summary,
                "evidence": output.profile.evidence,
            },
            generated_by=f"ai:{model_name}",
            generated_at=now,
            creator="nursing_plan_agent",
            updator="nursing_plan_agent",
        )
        db.add(profile)
        db.flush()
        plan = NursingPlan(
            plan_no=_business_no("PLAN"),
            patient_id=task.patient_id,
            encounter_id=task.encounter_id,
            profile_snapshot_id=profile.id,
            plan_status="ai_draft",
            risk_summary=output.risk_summary,
            education_summary=output.education_summary,
            handover_summary=output.handover_summary,
            generated_by=f"ai:{model_name}",
            creator="nursing_plan_agent",
            updator="nursing_plan_agent",
        )
        db.add(plan)
        db.flush()
        for item in output.items:
            db.add(
                NursingPlanItem(
                    nursing_plan_id=plan.id,
                    item_type=item.item_type,
                    item_code=item.item_code,
                    item_content=item.item_content,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    priority=item.priority,
                    nurse_action="pending",
                    creator="nursing_plan_agent",
                    updator="nursing_plan_agent",
                )
            )
        db.commit()
        db.refresh(plan)
        db.refresh(profile)
        return _to_dto(db, plan, profile)
    except Exception:
        db.rollback()
        raise


def update_nursing_plan(
    db: Session,
    task_ref: str | int,
    request: NursingPlanUpdateRequest,
    *,
    staff_id: int,
    operator: str,
) -> NursingPlanDto:
    """保存护士对 AI 草案摘要和计划项的编辑结果。"""
    task = _load_task(db, task_ref)
    _assert_task_owner(task, staff_id)
    row = _latest_plan_for_task(db, task)
    if row is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "护理计划不存在")
    plan, profile = row
    if plan.plan_status == "confirmed":
        raise AppError(ErrorCode.ERR_COMMON_001, "已确认护理计划不可直接修改")
    items = list(
        db.scalars(
            select(NursingPlanItem).where(
                NursingPlanItem.nursing_plan_id == plan.id,
                NursingPlanItem.deleted == 0,
            )
        ).all()
    )
    if {item.id for item in items} != {item.id for item in request.items}:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            "护理计划明细编号不完整或包含无效编号",
        )
    update_by_id = {item.id: item for item in request.items}
    plan.risk_summary = request.risk_summary
    plan.education_summary = request.education_summary
    plan.handover_summary = request.handover_summary
    plan.plan_status = "adjusted"
    plan.updator = operator
    for item in items:
        update = update_by_id[item.id]
        item.item_content = update.item_content
        item.priority = update.priority
        item.nurse_action = update.nurse_action
        item.nurse_comment = update.nurse_comment
        item.updator = operator
    db.commit()
    return _to_dto(db, plan, profile)


def confirm_nursing_plan(
    db: Session,
    task_ref: str | int,
    *,
    staff_id: int,
    operator: str,
) -> NursingPlanDto:
    """确认护理计划，使其成为当前有效护理指导方案。"""
    task = _load_task(db, task_ref)
    _assert_task_owner(task, staff_id)
    row = _latest_plan_for_task(db, task)
    if row is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "护理计划不存在")
    plan, profile = row
    items = list(
        db.scalars(
            select(NursingPlanItem).where(
                NursingPlanItem.nursing_plan_id == plan.id,
                NursingPlanItem.deleted == 0,
            )
        ).all()
    )
    pending = [item.id for item in items if item.nurse_action == "pending"]
    if pending:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            f"仍有 {len(pending)} 条护理建议未完成接受、修改或拒绝",
        )
    if not any(item.nurse_action != "rejected" for item in items):
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            "护理计划至少需要保留一条有效建议",
        )
    plan.plan_status = "confirmed"
    plan.confirmed_by = staff_id
    plan.confirmed_at = datetime.now(UTC)
    plan.updator = operator
    db.commit()
    return _to_dto(db, plan, profile)
