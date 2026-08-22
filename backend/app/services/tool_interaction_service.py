"""对话工具业务事件服务
作用：把 Agent 工具结果持久化为 interaction_event，发布患者/护士 SSE，
      并提供人工介入处理与知情同意签署接口的业务实现。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models import base as model_base
from app.models.interaction import (
    InteractionEvent as InteractionEventModel,
)
from app.models.interaction import (
    InteractionMessage,
    InteractionSession,
)
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.models.patient_portal import PatientNotification
from app.schemas.events import (
    BaseEvent,
    ConsentStatusUpdatedEvent,
    ConsentTriggeredEvent,
    EducationStatusUpdatedEvent,
    EducationTriggeredEvent,
    HandoffRequestedEvent,
    HandoffResolvedEvent,
)
from app.schemas.interaction_tools import (
    ConsentSignRequest,
    EducationAcknowledgeRequest,
    HandoffRequest,
    HandoffResolveRequest,
)
from app.workers.event_publisher import DialogEventPublisher, NurseEventPublisher

logger = logging.getLogger(__name__)

_SIGNATURE_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "storage" / "consent-signatures"
)
_SIGNATURE_DATA_PATTERN = re.compile(
    r"^data:image/(?P<format>png|jpeg);base64,(?P<data>[A-Za-z0-9+/=\s]+)$"
)
_MAX_SIGNATURE_BYTES = 5 * 1024 * 1024


def _load_task_context(
    db: Session,
    task_ref: int | str,
) -> tuple[CareTask, InteractionSession, Patient | None, PatientEncounter | None]:
    """加载任务、对话会话和患者床位快照。"""
    value = str(task_ref)
    conditions = [CareTask.task_no == value]
    if value.isdigit():
        conditions.append(CareTask.id == int(value))
    task = db.scalar(
        select(CareTask).where(or_(*conditions), CareTask.deleted == 0)
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    session = db.scalar(
        select(InteractionSession)
        .where(
            InteractionSession.task_id == task.id,
            InteractionSession.deleted == 0,
        )
        .order_by(InteractionSession.id.desc())
    )
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    return (
        task,
        session,
        db.get(Patient, task.patient_id),
        db.get(PatientEncounter, task.encounter_id),
    )


def _find_message_id(
    db: Session,
    session_id: int,
    message_no: str | None,
) -> int | None:
    """把消息业务编号转换为 interaction_message 主键。"""
    if not message_no:
        return None
    return db.scalar(
        select(InteractionMessage.id).where(
            InteractionMessage.interaction_session_id == session_id,
            InteractionMessage.message_no == message_no,
            InteractionMessage.deleted == 0,
        )
    )


def _persist_event(
    db: Session,
    *,
    session: InteractionSession,
    message_no: str | None,
    event_type: str,
    payload: dict[str, Any],
    handled_status: str = "pending",
    creator: str = "dialog_agent",
    source_invocation_id: str | None = None,
) -> InteractionEventModel:
    """保存结构化交互事件。"""
    record = InteractionEventModel(
        interaction_session_id=session.id,
        message_id=_find_message_id(db, session.id, message_no),
        event_type=event_type,
        event_payload=payload,
        handled_status=handled_status,
        source_invocation_id=source_invocation_id,
        creator=creator,
        updator=creator,
    )
    db.add(record)
    db.flush()
    return record


def _handoff_event(
    *,
    task: CareTask,
    session: InteractionSession,
    patient: Patient | None,
    encounter: PatientEncounter | None,
    result: dict[str, Any],
    message_no: str | None,
) -> HandoffRequestedEvent:
    """构造包含患者和床位信息的医护呼叫事件。"""
    return HandoffRequestedEvent(
        event_id=str(result.get("event_id") or f"HANDOFF-{uuid.uuid4()}"),
        session_id=session.session_no,
        task_id=task.id,
        message_id=message_no,
        request_id=str(result.get("request_id") or f"NURSE-{uuid.uuid4()}"),
        reason=str(result.get("reason") or "患者需要护士协助"),
        requested_action=str(result.get("requested_action") or "other"),
        action_label=str(result.get("action_label") or "人工护理操作"),
        urgency=str(result.get("urgency") or "routine"),
        priority=str(result.get("priority") or "high"),
        title=str(result.get("title") or "请求护士协助"),
        description=str(result.get("description") or result.get("reason") or ""),
        patient_name=patient.patient_name if patient else "",
        bed_no=encounter.bed_no if encounter else None,
        ward_name=encounter.ward_name if encounter else None,
        status=str(result.get("status") or "requested"),
        request_source=str(result.get("request_source") or "agent"),
        tool_name=(
            str(result["tool_name"]) if result.get("tool_name") else None
        ),
        tool_args=(
            dict(result["tool_args"]) if isinstance(result.get("tool_args"), dict) else None
        ),
        tool_result=(
            dict(result["tool_result"])
            if isinstance(result.get("tool_result"), dict)
            else None
        ),
    )


def _domain_event_from_result(
    *,
    task: CareTask,
    session: InteractionSession,
    patient: Patient | None,
    encounter: PatientEncounter | None,
    message_no: str | None,
    tool_name: str,
    result: dict[str, Any],
) -> BaseEvent | None:
    """将工具结果转换为前端可消费的领域事件。"""
    common = {
        "event_id": str(result.get("event_id") or uuid.uuid4()),
        "session_id": session.session_no,
        "task_id": task.id,
        "message_id": message_no,
        "tool_name": tool_name,
        "tool_args": dict(result.get("tool_args") or {}),
        "tool_result": dict(result.get("tool_result") or result),
    }
    if tool_name == "get_education_material":
        return EducationTriggeredEvent(
            **common,
            material_id=str(result["material_id"]),
            category=str(result["category"]),
            level=int(result["level"]),
            document_version=str(result["document_version"]),
            title=str(result["title"]),
            original_content=str(result["original_content"]),
            patient_content=str(result["patient_content"]),
            spoken_content=str(result["spoken_content"]),
            source_name=(
                str(result["source_name"]) if result.get("source_name") else None
            ),
            priority=str(result.get("priority") or "medium"),
            requires_acknowledgement=bool(
                result.get("requires_acknowledgement", True)
            ),
            auto_play=bool(result.get("auto_play", True)),
        )
    if tool_name == "trigger_consent_form":
        return ConsentTriggeredEvent(
            **common,
            form_id=str(result["form_id"]),
            form_type=str(result["form_type"]),
            title=str(result["title"]),
            document_version=str(result["document_version"]),
            full_text=str(result["full_text"]),
            clauses=list(result.get("clauses") or []),
            status=str(result.get("status") or "pending_signature"),
            requires_signature=bool(result.get("requires_signature", True)),
            auto_play=bool(result.get("auto_play", True)),
        )
    if tool_name == "request_nurse_assistance":
        return _handoff_event(
            task=task,
            session=session,
            patient=patient,
            encounter=encounter,
            result=result,
            message_no=message_no,
        )
    return None


def publish_tool_result(
    *,
    session_no: str,
    task_id: int | str | None,
    message_no: str | None,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: Any,
    publisher: DialogEventPublisher,
    source_invocation_id: str | None = None,
) -> BaseEvent | None:
    """持久化并发布 Agent 工具领域事件。"""
    if not isinstance(tool_result, dict) or not tool_result.get("success"):
        return None
    if model_base.SessionLocal is None:
        raise RuntimeError("数据库未初始化")

    with model_base.SessionLocal() as db:
        task, session, patient, encounter = _load_task_context(
            db,
            task_id or session_no,
        )
        source_key = (
            f"agent:{source_invocation_id}"
            if source_invocation_id
            else None
        )
        if source_key and db.scalar(
            select(InteractionEventModel.id).where(
                InteractionEventModel.interaction_session_id == session.id,
                InteractionEventModel.source_invocation_id == source_key,
                InteractionEventModel.deleted == 0,
            )
        ):
            logger.info(
                "忽略同一 Agent 调用的重复领域事件: session=%s call_id=%s",
                session.session_no,
                source_invocation_id,
            )
            return None
        result = dict(tool_result)
        result.setdefault("request_source", "agent")
        result.setdefault("tool_name", tool_name)
        result.setdefault("tool_args", dict(tool_args))
        result.setdefault("tool_result", dict(tool_result))
        domain_event = _domain_event_from_result(
            task=task,
            session=session,
            patient=patient,
            encounter=encounter,
            message_no=message_no,
            tool_name=tool_name,
            result=result,
        )
        if domain_event is None:
            return None

        if tool_name == "request_nurse_assistance":
            session.handoff_required = True
            session.handoff_reason = str(result.get("reason") or "")
            task.need_manual_intervention = True
            task.intervention_reason = session.handoff_reason

        _persist_event(
            db,
            session=session,
            message_no=message_no,
            event_type=domain_event.event_type.value,
            payload={
                "tool_name": tool_name,
                "tool_args": tool_args,
                "source_invocation_id": source_invocation_id,
                **domain_event.model_dump(mode="json"),
            },
            source_invocation_id=source_key,
        )
        db.commit()

        publisher.publish(domain_event)
        if (
            isinstance(domain_event, HandoffRequestedEvent)
            and task.assigned_nurse_id is not None
        ):
            NurseEventPublisher(
                task.assigned_nurse_id,
                publisher.redis,
            ).publish(domain_event)
        return domain_event


def _new_handoff_result(request: HandoffRequest) -> dict[str, Any]:
    """构造前端主动呼叫的统一工具结果。"""
    action_labels = {
        "measure_temperature": "测量体温",
        "measure_blood_pressure": "测量血压",
        "measure_weight": "测量体重",
        "measure_height": "测量身高",
        "other": "人工护理协助",
    }
    action_label = action_labels[request.requested_action]
    return {
        "success": True,
        "event_id": f"HANDOFF-EVENT-{uuid.uuid4().hex.upper()}",
        "request_id": f"NURSE-{uuid.uuid4().hex.upper()}",
        "requested_action": request.requested_action,
        "action_label": action_label,
        "reason": request.reason.strip(),
        "urgency": request.urgency,
        "priority": "high" if request.urgency == "urgent" else "medium",
        "title": f"需要护士协助{action_label}",
        "description": request.reason.strip(),
        "status": "requested",
        "request_source": "patient",
    }


def request_handoff(
    db: Session,
    task_ref: str,
    request: HandoffRequest,
    *,
    patient_id: int,
) -> dict[str, Any]:
    """患者端主动呼叫护士并推送责任护士全局提醒。"""
    task, session, patient, encounter = _load_task_context(db, task_ref)
    if session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权呼叫该任务护士")
    source_key = (
        f"patient:{request.client_invocation_id}"
        if request.client_invocation_id
        else None
    )
    if source_key:
        existing = db.scalar(
            select(InteractionEventModel).where(
                InteractionEventModel.interaction_session_id == session.id,
                InteractionEventModel.source_invocation_id == source_key,
                InteractionEventModel.deleted == 0,
            )
        )
        if existing is not None:
            logger.info(
                "复用患者主动呼叫事件: session=%s invocation=%s",
                session.session_no,
                request.client_invocation_id,
            )
            return _interaction_event_payload(existing)
    result = _new_handoff_result(request)
    event = _handoff_event(
        task=task,
        session=session,
        patient=patient,
        encounter=encounter,
        result=result,
        message_no=None,
    )
    session.handoff_required = True
    session.handoff_reason = request.reason.strip()
    task.need_manual_intervention = True
    task.intervention_reason = session.handoff_reason
    _persist_event(
        db,
        session=session,
        message_no=None,
        event_type=event.event_type.value,
        payload={
            **event.model_dump(mode="json"),
            "client_invocation_id": request.client_invocation_id,
        },
        creator="patient",
        source_invocation_id=source_key,
    )
    db.add(
        PatientNotification(
            notification_no=f"PN-{uuid.uuid4().hex.upper()}",
            patient_id=patient.id,
            encounter_id=encounter.id if encounter else None,
            notification_type="handoff",
            title="护士协助请求已提交",
            content="护士已收到您的请求，请在床旁等待处理。",
            priority="high" if request.urgency == "urgent" else "normal",
            payload={"request_id": event.request_id, "task_id": task.id},
            creator="patient",
            updator="patient",
        )
    )
    db.commit()
    publisher = DialogEventPublisher(session.session_no)
    publisher.publish(event)
    if task.assigned_nurse_id is not None:
        NurseEventPublisher(task.assigned_nurse_id, publisher.redis).publish(event)
    return event.model_dump(mode="json")


def _resolve_pending_handoff_rows(
    rows: list[InteractionEventModel],
    *,
    request_id: str | None,
    staff_id: int,
    staff_no: str,
    staff_name: str,
    handled_at: datetime,
    resolution: str | None,
) -> list[str]:
    """更新呼叫请求的永久处理快照，并返回本次处理的请求编号。"""
    request_ids: list[str] = []
    for row in rows:
        row_request_id = str((row.event_payload or {}).get("request_id") or "")
        if row.handled_status == "resolved":
            continue
        if request_id is not None and row_request_id != request_id:
            continue
        if row_request_id:
            request_ids.append(row_request_id)
        row.handled_status = "resolved"
        row.handled_by = str(staff_id)
        row.handled_at = handled_at
        row.updator = str(staff_id)
        payload = dict(row.event_payload or {})
        payload.update(
            {
                "status": "resolved",
                "resolved_by_staff_id": str(staff_id),
                "resolved_by_staff_no": staff_no,
                "resolved_by_name": staff_name,
                "handled_at": handled_at.isoformat(),
                "resolution": resolution,
            }
        )
        row.event_payload = payload
    return request_ids


def resolve_handoff(
    db: Session,
    task_ref: str,
    request: HandoffResolveRequest,
    *,
    staff_id: int,
    staff_no: str,
    staff_name: str,
) -> dict[str, Any]:
    """医护处理当前任务全部未完成呼叫，并通知患者端。"""
    task, session, _, _ = _load_task_context(db, task_ref)
    requested_rows = list(
        db.scalars(
            select(InteractionEventModel)
            .where(
                InteractionEventModel.interaction_session_id == session.id,
                InteractionEventModel.event_type
                == HandoffRequestedEvent.model_fields["event_type"].default.value,
                InteractionEventModel.deleted == 0,
            )
            .order_by(InteractionEventModel.id.asc())
        ).all()
    )
    handled_at = datetime.now(UTC)
    request_ids = _resolve_pending_handoff_rows(
        requested_rows,
        request_id=request.request_id,
        staff_id=staff_id,
        staff_no=staff_no,
        staff_name=staff_name,
        handled_at=handled_at,
        resolution=request.resolution,
    )
    remaining_pending = any(
        row.handled_status != "resolved" for row in requested_rows
    )
    session.handoff_required = remaining_pending
    session.handoff_reason = (
        next(
            (
                str((row.event_payload or {}).get("reason") or "")
                for row in requested_rows
                if row.handled_status != "resolved"
            ),
            None,
        )
        if remaining_pending
        else None
    )
    task.need_manual_intervention = remaining_pending
    task.intervention_reason = session.handoff_reason

    event = HandoffResolvedEvent(
        event_id=f"HANDOFF-RESOLVED-{uuid.uuid4().hex.upper()}",
        session_id=session.session_no,
        task_id=task.id,
        request_id=request_ids[-1] if request_ids else request.request_id,
        request_ids=request_ids,
        resolved_by=staff_name,
        resolved_by_staff_id=str(staff_id),
        resolved_by_staff_no=staff_no,
        resolved_by_name=staff_name,
        handled_at=handled_at,
        remaining_pending=remaining_pending,
        resolution=request.resolution,
    )
    _persist_event(
        db,
        session=session,
        message_no=None,
        event_type=event.event_type.value,
        payload=event.model_dump(mode="json"),
        handled_status="resolved",
        creator=str(staff_id),
    )
    db.commit()
    publisher = DialogEventPublisher(session.session_no)
    publisher.publish(event)
    if task.assigned_nurse_id is not None:
        NurseEventPublisher(task.assigned_nurse_id, publisher.redis).publish(event)
    return event.model_dump(mode="json")


def _save_signature_file(signature_data: str) -> tuple[str, bytes]:
    """校验并保存患者手写签名图片。"""
    match = _SIGNATURE_DATA_PATTERN.match(signature_data.strip())
    if match is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "签名图片格式无效")
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except ValueError as exc:
        raise AppError(ErrorCode.ERR_COMMON_001, "签名图片数据无效") from exc
    if not raw or len(raw) > _MAX_SIGNATURE_BYTES:
        raise AppError(ErrorCode.ERR_COMMON_001, "签名图片为空或超过 5MB")
    image_format = match.group("format")
    if image_format == "png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AppError(ErrorCode.ERR_COMMON_001, "签名 PNG 文件头无效")
    if image_format == "jpeg" and not raw.startswith(b"\xff\xd8"):
        raise AppError(ErrorCode.ERR_COMMON_001, "签名 JPEG 文件头无效")
    _SIGNATURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    suffix = "jpg" if image_format == "jpeg" else "png"
    filename = f"{uuid.uuid4().hex}.{suffix}"
    (_SIGNATURE_DIRECTORY / filename).write_bytes(raw)
    return f"/api/consent-forms/signatures/{filename}", raw


def submit_consent(
    db: Session,
    task_ref: str,
    request: ConsentSignRequest,
    *,
    patient_id: int,
) -> dict[str, Any]:
    """保存患者知情同意决定和签名文件，并发布状态事件。"""
    task, session, _, _ = _load_task_context(db, task_ref)
    if session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权签署该任务文档")
    if str(request.task_id) not in {str(task.id), task.task_no}:
        raise AppError(ErrorCode.ERR_DIALOG_004, "task_id 与知情同意任务不匹配")
    if request.decision == "agreed" and not request.signature_data:
        raise AppError(ErrorCode.ERR_COMMON_001, "同意签署时必须提供手写签名")

    signature_file_url: str | None = None
    signature_bytes = b""
    if request.signature_data:
        signature_file_url, signature_bytes = _save_signature_file(
            request.signature_data
        )
    canonical_content = json.dumps(
        {
            "form_id": request.form_id,
            "document_version": request.document_version,
            "decision": request.decision,
            "clauses": request.clauses,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signed_content_hash = hashlib.sha256(
        canonical_content + signature_bytes
    ).hexdigest()
    completed_at = datetime.now(UTC)
    status = {
        "agreed": "signed",
        "refused": "refused",
        "needs_explanation": "needs_explanation",
    }[request.decision]
    payload = {
        "form_id": request.form_id,
        "document_version": request.document_version,
        "participant_name": request.participant_name,
        "decision": request.decision,
        "status": status,
        "clauses": request.clauses,
        "signature_file_url": signature_file_url,
        "signed_content_hash": signed_content_hash,
        "completed_at": completed_at.isoformat(),
    }
    event = ConsentStatusUpdatedEvent(
        event_id=f"CONSENT-STATUS-{uuid.uuid4().hex.upper()}",
        session_id=session.session_no,
        task_id=task.id,
        form_id=request.form_id,
        status=status,
        decision=request.decision,
        clauses=request.clauses,
        signature_file_url=signature_file_url,
        completed_at=completed_at,
    )
    _persist_event(
        db,
        session=session,
        message_no=None,
        event_type=event.event_type.value,
        payload=payload,
        handled_status="completed" if request.decision == "agreed" else "pending",
        creator="patient",
    )
    if request.decision == "needs_explanation":
        session.handoff_required = True
        session.handoff_reason = "患者对知情同意内容需要护士人工解释"
        task.need_manual_intervention = True
        task.intervention_reason = session.handoff_reason
    db.commit()
    # 批次 B 结构化知情同意记录与旧 interaction_event 同步写入。
    # 历史任务可能尚未配置文档模板，保留旧接口兼容并由快照接口返回明确不可用。
    try:
        from app.services.patient_portal_service import attach_consent_signature

        attach_consent_signature(
            db,
            task_ref=task_ref,
            patient_id=patient_id,
            encounter_id=task.encounter_id,
            participant_name=request.participant_name,
            participant_type="患者",
            signature_file_url=signature_file_url,
            signed_content_hash=signed_content_hash,
        )
    except AppError as exc:
        if exc.code != ErrorCode.ERR_PATIENT_009:
            raise
        logger.warning(
            "任务尚未配置结构化知情同意文档，保留旧事件签署结果: task=%s",
            task.task_no,
        )
    DialogEventPublisher(session.session_no).publish(event)
    return payload


def _find_education_acknowledgement(
    rows: list[InteractionEventModel],
    *,
    source_event_id: str,
    material_id: str,
) -> InteractionEventModel | None:
    """查找同一宣教事件已经保存的确认结果
    作用：支持浏览器超时重试和重复点击时幂等返回，避免重复写入状态事件。
    Args:
        - rows: 当前会话的宣教状态事件，按新到旧排列
        - source_event_id: 宣教领域事件编号
        - material_id: 宣教材料编号
    Return:
        - 已存在的确认事件；未确认时返回 None
    """
    for row in rows:
        payload = row.event_payload or {}
        if (
            str(payload.get("source_event_id") or "") == source_event_id
            and str(payload.get("material_id") or "") == material_id
            and bool(payload.get("acknowledged"))
        ):
            return row
    return None


def acknowledge_education(
    db: Session,
    task_ref: str,
    request: EducationAcknowledgeRequest,
    *,
    patient_id: int,
) -> dict[str, Any]:
    """持久化患者已阅读宣教材料的操作结果，并通知医护端。"""
    task, session, _, _ = _load_task_context(db, task_ref)
    if session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权确认该任务宣教")
    if str(request.task_id) not in {str(task.id), task.task_no}:
        raise AppError(ErrorCode.ERR_DIALOG_004, "task_id 与宣教任务不匹配")

    material_event = db.scalar(
        select(InteractionEventModel)
        .where(
            InteractionEventModel.interaction_session_id == session.id,
            InteractionEventModel.event_type
            == EducationTriggeredEvent.model_fields["event_type"].default.value,
            InteractionEventModel.event_payload["event_id"].astext
            == request.event_id,
            InteractionEventModel.deleted == 0,
        )
        .order_by(InteractionEventModel.id.desc())
    )
    if material_event is None or str(
        (material_event.event_payload or {}).get("material_id") or ""
    ) != request.material_id:
        raise AppError(ErrorCode.ERR_COMMON_001, "宣教材料不存在或已失效")

    status_rows = list(
        db.scalars(
            select(InteractionEventModel)
            .where(
                InteractionEventModel.interaction_session_id == session.id,
                InteractionEventModel.event_type
                == EducationStatusUpdatedEvent.model_fields["event_type"].default.value,
                InteractionEventModel.deleted == 0,
            )
            .order_by(InteractionEventModel.id.desc())
        ).all()
    )
    existing_status = _find_education_acknowledgement(
        status_rows,
        source_event_id=request.event_id,
        material_id=request.material_id,
    )
    if existing_status is not None:
        return _interaction_event_payload(existing_status)

    acknowledged_at = datetime.now(UTC)
    event = EducationStatusUpdatedEvent(
        event_id=f"EDUCATION-STATUS-{uuid.uuid4().hex.upper()}",
        session_id=session.session_no,
        task_id=task.id,
        source_event_id=request.event_id,
        material_id=request.material_id,
        status="acknowledged",
        acknowledged=True,
        acknowledged_at=acknowledged_at,
    )
    _persist_event(
        db,
        session=session,
        message_no=None,
        event_type=event.event_type.value,
        payload=event.model_dump(mode="json"),
        handled_status="completed",
        creator="patient",
    )
    db.commit()
    DialogEventPublisher(session.session_no).publish(event)
    return event.model_dump(mode="json")


def _interaction_event_payload(row: InteractionEventModel) -> dict[str, Any]:
    """组装历史事件 payload，并保留事件自身已持久化的处理时间。"""
    payload = dict(row.event_payload or {})
    payload["handled_status"] = row.handled_status
    payload["handled_by"] = row.handled_by
    payload["handled_at"] = (
        row.handled_at.isoformat()
        if row.handled_at
        else payload.get("handled_at")
    )
    return payload


def _coalesce_legacy_patient_handoffs(
    rows: list[InteractionEventModel],
) -> list[tuple[InteractionEventModel, dict[str, Any]]]:
    """合并旧版本中同一次患者点击产生的毫秒级重复呼叫
    作用：旧事件没有 `request_source` 和调用编号，只对明确非 Agent、
          内容完全相同且间隔不超过一秒的相邻记录做展示兼容。
          新事件和不同 Agent call_id 不参与合并。
    """
    result: list[tuple[InteractionEventModel, dict[str, Any]]] = []
    legacy_group: tuple[
        tuple[str, str, str],
        InteractionEventModel,
        dict[str, Any],
    ] | None = None
    for row in rows:
        payload = _interaction_event_payload(row)
        is_legacy_patient_handoff = (
            row.event_type == "handoff_requested"
            and row.source_invocation_id is None
            and not payload.get("request_source")
            and not payload.get("tool_name")
        )
        signature = (
            str(payload.get("reason") or payload.get("description") or ""),
            str(payload.get("requested_action") or "other"),
            str(payload.get("urgency") or "routine"),
        )
        if (
            is_legacy_patient_handoff
            and legacy_group is not None
            and legacy_group[0] == signature
            and abs(
                (row.create_time - legacy_group[1].create_time).total_seconds()
            )
            <= 1
        ):
            canonical_payload = legacy_group[2]
            request_ids = list(
                canonical_payload.get("legacy_duplicate_request_ids") or []
            )
            duplicate_request_id = payload.get("request_id")
            if duplicate_request_id and duplicate_request_id not in request_ids:
                request_ids.append(duplicate_request_id)
            canonical_payload["legacy_duplicate_request_ids"] = request_ids
            if (
                row.handled_status == "resolved"
                or payload.get("status") == "resolved"
            ):
                for key in (
                    "status",
                    "handled_status",
                    "handled_by",
                    "handled_at",
                    "resolved_by_staff_id",
                    "resolved_by_staff_no",
                    "resolved_by_name",
                    "resolution",
                ):
                    if payload.get(key) is not None:
                        canonical_payload[key] = payload[key]
                canonical_payload["status"] = "resolved"
                canonical_payload["handled_status"] = "resolved"
            continue

        result.append((row, payload))
        legacy_group = (
            (signature, row, payload)
            if is_legacy_patient_handoff
            else None
        )
    return result


def list_interaction_events(
    db: Session,
    session_no: str,
    *,
    patient_id: int | None = None,
) -> list[dict[str, Any]]:
    """查询会话中的宣教、同意和医护呼叫事件快照。"""
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    if patient_id is not None and session.patient_id != patient_id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权访问该会话事件")
    rows = list(
        db.scalars(
            select(InteractionEventModel)
            .where(
                InteractionEventModel.interaction_session_id == session.id,
                InteractionEventModel.event_type.in_(
                    [
                        "education_triggered",
                        "education_status_updated",
                        "consent_triggered",
                        "consent_status_updated",
                        "handoff_requested",
                        "handoff_resolved",
                    ]
                ),
                InteractionEventModel.deleted == 0,
            )
            .order_by(
                InteractionEventModel.create_time.asc(),
                InteractionEventModel.id.asc(),
            )
        ).all()
    )
    return [
        {
            "event_id": str(payload.get("event_id") or row.id),
            "event_type": row.event_type,
            "task_id": str(session.task_id),
            "session_id": session.session_no,
            "message_id": (
                str(row.message_id) if row.message_id is not None else None
            ),
            "occurred_at": row.create_time.isoformat(),
            "payload": payload,
        }
        for row, payload in _coalesce_legacy_patient_handoffs(rows)
    ]
