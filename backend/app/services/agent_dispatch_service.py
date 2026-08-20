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
    """按 Schedule prepare → Dialog 预热 → AI 首问顺序派发后台准备任务。"""
    from celery import chain

    from app.celery_app.tasks import (
        dialog_agent_preheat,
        dialog_agent_worker,
        schedule_agent_worker,
    )

    patient_info, task_config = build_session_agent_payload(db, session)
    prepared_config = {**task_config, "patient_info": patient_info}
    try:
        chain(
            schedule_agent_worker.si(session.session_no, prepared_config),
            dialog_agent_preheat.si(
                session.session_no,
                patient_info,
                prepared_config,
            ),
            dialog_agent_worker.si(
                session.session_no,
                patient_info,
                prepared_config,
            ),
        ).apply_async()
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
    """独立派发 Dialog、Schedule observe 与 Extraction。
    Dialog 只读取后台最后一次成功结果，不等待另外两个 Agent。
    """
    from app.celery_app.tasks import (
        dialog_agent_worker,
        extraction_agent_worker,
        schedule_agent_worker,
    )

    patient_info, task_config = build_session_agent_payload(db, session)
    turn_config = {
        **task_config,
        "patient_info": patient_info,
        "source_message_id": source_message_id,
        "source_event_id": source_event_id,
    }
    try:
        dialog_agent_worker.delay(
            session.session_no,
            patient_info,
            turn_config,
        )
    except Exception as exc:
        logger.exception(
            "患者答案 Dialog 任务派发失败: session=%s message=%s",
            session.session_no,
            source_message_id,
        )
        raise AppError(
            ErrorCode.ERR_TASK_005,
            f"后台任务派发失败: {type(exc).__name__}",
            http_status=503,
        ) from exc

    for agent_name, task in (
        ("schedule", schedule_agent_worker),
        ("extraction", extraction_agent_worker),
    ):
        try:
            task.delay(session.session_no, turn_config)
        except Exception:
            logger.exception(
                "后台 %s 任务派发失败，不阻塞患者对话: session=%s message=%s",
                agent_name,
                session.session_no,
                source_message_id,
            )


def dispatch_voice_answer_workers(
    session_no: str,
    *,
    task_id: int,
    scale_codes: list[str],
    source_message_id: str,
    source_event_id: str | None,
    patient_info: dict,
) -> None:
    """仅派发语音模式的 Schedule / Extraction。

    语音模型已经由 Voice Gateway 完成当前轮回复，不能再派发
    `dialog_agent_worker`，否则会产生第二条 AI 问句。文本模式入口
    `dispatch_answer_workers` 保持原行为不变。
    """
    from app.celery_app.tasks import extraction_agent_worker, schedule_agent_worker

    turn_config = {
        "task_id": task_id,
        "scale_codes": scale_codes,
        "patient_info": patient_info,
        "source_message_id": source_message_id,
        "source_event_id": source_event_id,
        "check_interval": 1,
        "interaction_mode": "voice",
    }
    for agent_name, task in (
        ("schedule", schedule_agent_worker),
        ("extraction", extraction_agent_worker),
    ):
        try:
            task.delay(session_no, turn_config)
        except Exception:
            logger.exception(
                "语音模式后台 %s 任务派发失败，不阻塞语音响应: session=%s message=%s",
                agent_name,
                session_no,
                source_message_id,
            )
