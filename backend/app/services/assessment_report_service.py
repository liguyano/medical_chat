"""评估报告服务
作用：聚合最终评估事实、调用语言模型生成综合报告并按版本持久化。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from medagent.providers import create_chat_model
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_report import AssessmentReport
from app.models.patient_task import CareTask
from app.schemas.assessment_report import (
    AiAssessmentReportOutput,
    AssessmentReportDto,
    AssessmentReportVersionDto,
)
from app.services.nursing_plan_service import build_generation_source


def _load_task(db: Session, task_ref: str | int) -> CareTask:
    """按主键或任务编号加载护理任务。"""
    value = str(task_ref)
    conditions = [CareTask.task_no == value]
    if value.isdigit():
        conditions.append(CareTask.id == int(value))
    task = db.scalar(
        select(CareTask).where(or_(*conditions), CareTask.deleted == 0)
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    return task


def _assert_task_owner(task: CareTask, staff_id: int) -> None:
    """限制报告由任务责任护士访问。"""
    if task.assigned_nurse_id is not None and task.assigned_nurse_id != staff_id:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            "当前任务不属于登录医护人员",
            http_status=403,
        )


def _message_text(content: Any) -> str:
    """提取 LangChain 消息文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text") if isinstance(item, dict) else item)
            for item in content
            if not isinstance(item, dict) or item.get("text")
        )
    return str(content or "")


def _parse_model_output(content: Any) -> AiAssessmentReportOutput:
    """提取并校验模型返回的报告 JSON。"""
    text = _message_text(content).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return AiAssessmentReportOutput.model_validate_json(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return AiAssessmentReportOutput.model_validate_json(text[start : end + 1])


async def generate_ai_report(
    source: dict[str, Any],
    *,
    model: BaseChatModel | None = None,
) -> tuple[AiAssessmentReportOutput, str]:
    """调用真实语言模型生成综合评估报告。"""
    model_name = "injected-test-model"
    if model is None:
        config = get_app_config()
        model_config = (
            config.get_agent_model_config("assessment_report_agent")
            or config.get_agent_model_config("nursing_plan_agent")
            or config.get_agent_model_config("extraction_agent")
        )
        if model_config is None:
            raise RuntimeError("未配置评估报告、护理计划或抽取语言模型")
        model_config = model_config.model_copy(update={"enable_thinking": False})
        model_name = model_config.name
        model = create_chat_model(model_config)

    schema = AiAssessmentReportOutput.model_json_schema()
    response = await model.ainvoke(
        [
            SystemMessage(
                content=(
                    "你是住院护理评估报告辅助生成器。只能根据输入的量表事实进行归纳，"
                    "不得修改分数、虚构诊断、药物、检查结果或已执行的护理措施。"
                    "量表原始结果由系统单独展示，你只生成综合摘要、重点发现、风险概览、"
                    "护理关注点和复评建议。输出必须是单个 JSON 对象，不要 Markdown。"
                )
            ),
            HumanMessage(
                content=(
                    f"输出 JSON Schema：{json.dumps(schema, ensure_ascii=False)}\n"
                    f"评估事实：{json.dumps(source, ensure_ascii=False, default=str)}"
                )
            ),
        ]
    )
    return _parse_model_output(response.content), model_name


def _history(db: Session, task_id: int) -> list[AssessmentReport]:
    """读取任务全部有效报告版本。"""
    return list(
        db.scalars(
            select(AssessmentReport)
            .where(
                AssessmentReport.task_id == task_id,
                AssessmentReport.deleted == 0,
            )
            .order_by(AssessmentReport.version_no.desc(), AssessmentReport.id.desc())
        ).all()
    )


def _version_dto(report: AssessmentReport) -> AssessmentReportVersionDto:
    """转换报告版本摘要。"""
    return AssessmentReportVersionDto(
        id=report.id,
        version_no=report.version_no,
        report_status=report.report_status,
        generated_by=report.generated_by,
        generated_at=report.generated_at.isoformat(),
        confirmed_by=report.confirmed_by,
        confirmed_at=report.confirmed_at.isoformat() if report.confirmed_at else None,
    )


def _to_dto(
    report: AssessmentReport,
    history: list[AssessmentReport],
) -> AssessmentReportDto:
    """转换完整报告响应。"""
    return AssessmentReportDto(
        **_version_dto(report).model_dump(),
        report_no=report.report_no,
        task_id=report.task_id,
        source_submission_ids=[int(item) for item in report.source_submission_ids],
        source_snapshot=report.source_snapshot,
        report_content=AiAssessmentReportOutput.model_validate(report.report_content),
        versions=[_version_dto(item) for item in history],
    )


def get_assessment_report(
    db: Session,
    task_ref: str | int,
    *,
    staff_id: int,
    version_no: int | None = None,
) -> AssessmentReportDto | None:
    """查询最新或指定版本评估报告。"""
    task = _load_task(db, task_ref)
    _assert_task_owner(task, staff_id)
    history = _history(db, task.id)
    if not history:
        return None
    report = next(
        (item for item in history if item.version_no == version_no),
        history[0] if version_no is None else None,
    )
    if report is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "指定评估报告版本不存在", 404)
    return _to_dto(report, history)


async def generate_assessment_report(
    db: Session,
    task_ref: str | int,
    *,
    staff_id: int,
    force: bool = False,
    model: BaseChatModel | None = None,
) -> AssessmentReportDto:
    """生成并保存一个新的评估报告版本。"""
    task = _load_task(db, task_ref)
    _assert_task_owner(task, staff_id)
    if task.task_status != "completed":
        raise AppError(ErrorCode.ERR_COMMON_001, "请先完成护士评估复核再生成报告")
    history = _history(db, task.id)
    if history and not force:
        return _to_dto(history[0], history)

    source, submission_ids = build_generation_source(db, task)
    output, model_name = await generate_ai_report(source, model=model)
    version_no = int(
        db.scalar(
            select(func.coalesce(func.max(AssessmentReport.version_no), 0)).where(
                AssessmentReport.task_id == task.id,
                AssessmentReport.deleted == 0,
            )
        )
        or 0
    ) + 1
    now = datetime.now(UTC)
    report = AssessmentReport(
        report_no=f"REPORT-{uuid.uuid4().hex[:16].upper()}",
        task_id=task.id,
        version_no=version_no,
        report_status="generated",
        source_submission_ids=submission_ids,
        source_snapshot=source,
        report_content=output.model_dump(mode="json"),
        generated_by=f"ai:{model_name}",
        generated_at=now,
        creator=str(staff_id),
        updator=str(staff_id),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _to_dto(report, [report, *history])


def confirm_assessment_report(
    db: Session,
    task_ref: str | int,
    *,
    staff_id: int,
) -> AssessmentReportDto:
    """确认最新评估报告版本。"""
    task = _load_task(db, task_ref)
    _assert_task_owner(task, staff_id)
    history = _history(db, task.id)
    if not history:
        raise AppError(ErrorCode.ERR_COMMON_001, "评估报告尚未生成")
    report = history[0]
    report.report_status = "confirmed"
    report.confirmed_by = staff_id
    report.confirmed_at = datetime.now(UTC)
    report.updator = str(staff_id)
    db.commit()
    db.refresh(report)
    return _to_dto(report, history)
