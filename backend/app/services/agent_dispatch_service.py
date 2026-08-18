"""Agent 单轮任务派发服务
作用：统一构造会话 Agent 上下文，并派发首问或患者答案处理流水线。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import AssessmentInstance
from app.models.assessment_template import AssessmentScale
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask, Patient, PatientEncounter

logger = logging.getLogger(__name__)


def _calculate_age(birthday: date | None) -> int | None:
    """计算患者年龄。"""
    if birthday is None:
        return None
    today = datetime.now(UTC).date()
    return today.year - birthday.year - (
        (today.month, today.day) < (birthday.month, birthday.day)
    )


def build_session_agent_payload(
    db: Session,
    session: InteractionSession,
) -> tuple[dict, dict]:
    """构造 Agent 所需患者信息和任务配置。"""
    task = db.get(CareTask, session.task_id)
    patient = db.get(Patient, session.patient_id)
    encounter = db.get(PatientEncounter, session.encounter_id)
    if task is None or patient is None or encounter is None:
        raise AppError(ErrorCode.ERR_DIALOG_001, "会话关联业务数据不存在")

    scale_codes = list(
        db.scalars(
            select(AssessmentScale.scale_code)
            .join(
                AssessmentInstance,
                AssessmentInstance.scale_id == AssessmentScale.id,
            )
            .where(
                AssessmentInstance.task_id == task.id,
                AssessmentInstance.deleted == 0,
                AssessmentScale.deleted == 0,
            )
            .order_by(AssessmentInstance.id.asc())
        ).all()
    )
    if not scale_codes:
        raise AppError(ErrorCode.ERR_DIALOG_002, "会话未配置已发布量表")

    patient_info = {
        "patient_id": patient.id,
        "encounter_id": encounter.id,
        "name": patient.patient_name,
        "gender": patient.sex or "",
        "age": _calculate_age(patient.birthday),
        "department": encounter.department_name or "",
        "bed_no": encounter.bed_no or "",
    }
    task_config = {
        "task_id": task.id,
        "task_no": task.task_no,
        "scale_codes": scale_codes,
        "engine_type": "text",
        "check_interval": 1,
    }
    return patient_info, task_config


def dispatch_opening_workers(
    db: Session,
    session: InteractionSession,
) -> None:
    """派发预热和 AI 首问任务。"""
    from app.celery_app.tasks import dialog_agent_preheat, dialog_agent_worker

    patient_info, task_config = build_session_agent_payload(db, session)
    try:
        dialog_agent_preheat.delay(session.session_no, patient_info, task_config)
        dialog_agent_worker.delay(session.session_no, patient_info, task_config)
    except Exception as exc:
        logger.exception("AI 首问任务派发失败: session=%s", session.session_no)
        raise AppError(
            ErrorCode.ERR_TASK_005,
            f"后台任务派发失败: {type(exc).__name__}",
            http_status=503,
        ) from exc


def dispatch_answer_workers(
    db: Session,
    session: InteractionSession,
    *,
    source_message_id: str,
    source_event_id: str | None,
) -> None:
    """按 Schedule → Dialog + Extraction 顺序派发患者答案流水线。"""
    from celery import chain, group

    from app.celery_app.tasks import (
        dialog_agent_worker,
        extraction_agent_worker,
        schedule_agent_worker,
    )

    patient_info, task_config = build_session_agent_payload(db, session)
    turn_config = {
        **task_config,
        "source_message_id": source_message_id,
        "source_event_id": source_event_id,
    }
    try:
        workflow = chain(
            schedule_agent_worker.si(session.session_no, turn_config),
            group(
                dialog_agent_worker.si(
                    session.session_no,
                    patient_info,
                    turn_config,
                ),
                extraction_agent_worker.si(session.session_no, turn_config),
            ),
        )
        workflow.apply_async()
    except Exception as exc:
        logger.exception(
            "患者答案 Agent 流水线派发失败: session=%s message=%s",
            session.session_no,
            source_message_id,
        )
        raise AppError(
            ErrorCode.ERR_TASK_005,
            f"后台任务派发失败: {type(exc).__name__}",
            http_status=503,
        ) from exc
