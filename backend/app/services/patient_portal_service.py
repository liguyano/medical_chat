"""患者门户业务服务。

作用：实现患者身份入口、一次性扫码、通知/病区指南、住院助手和知情同意
快照等能力。所有方法都要求调用方先通过患者 HttpOnly 会话或医护会话完成
授权；助手与护理评估会话使用完全独立的表和消息链路。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.patient_portal import (
    ConsentClause,
    ConsentClauseRecord,
    ConsentDocument,
    ConsentDocumentVersion,
    ConsentParticipant,
    ConsentRecord,
    ConsentSignature,
    ContentDeliveryItem,
    ContentDeliverySession,
    ContentPlaybackEvent,
    PatientAssistantMessage,
    PatientAssistantSession,
    PatientNotification,
    WardGuide,
)
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.schemas.patient_portal import (
    ConsentClauseConfirmRequest,
    ConsentPlaybackRequest,
    PatientAssistantMessageDto,
    PatientAssistantSessionDto,
    PatientNotificationDto,
    WardGuideDto,
)
from app.services import patient_service
from app.utils.patient_identity import decrypt_id_card, normalize_id_card
from app.utils.redis_client import get_redis

VERIFY_LIMIT = 5
VERIFY_WINDOW_SECONDS = 600
SCAN_TOKEN_PREFIX = "patient_scan_token:"
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _task_for_patient(
    db: Session,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
) -> CareTask:
    """加载当前患者当前住院记录下的任务，避免任务编号枚举其他患者。"""
    value = str(task_ref)
    conditions = [CareTask.task_no == value]
    if value.isdigit():
        conditions.append(CareTask.id == int(value))
    task = db.scalar(
        select(CareTask).where(
            or_(*conditions),
            CareTask.patient_id == patient_id,
            CareTask.encounter_id == encounter_id,
            CareTask.deleted == 0,
        )
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    return task


def _task_by_no(db: Session, task_no: str) -> tuple[CareTask, Patient, PatientEncounter]:
    """加载扫码/身份核验使用的任务及在院上下文。"""
    task = db.scalar(
        select(CareTask).where(
            CareTask.task_no == task_no.strip(),
            CareTask.deleted == 0,
        )
    )
    if task is None:
        raise AppError(ErrorCode.ERR_PATIENT_001)
    patient = db.scalar(
        select(Patient).where(Patient.id == task.patient_id, Patient.deleted == 0)
    )
    encounter = db.scalar(
        select(PatientEncounter).where(
            PatientEncounter.id == task.encounter_id,
            PatientEncounter.patient_id == task.patient_id,
            PatientEncounter.encounter_status == "在院",
            PatientEncounter.deleted == 0,
        )
    )
    if patient is None or encounter is None:
        raise AppError(ErrorCode.ERR_PATIENT_002)
    return task, patient, encounter


def _verify_rate_key(request: Request, task_no: str) -> str:
    """生成不暴露完整身份的 Redis 限流键。"""
    client_host = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(f"{client_host}:{task_no}".encode()).hexdigest()[:32]
    return f"patient_verify_attempt:{digest}"


def _check_verify_limit(request: Request, task_no: str) -> str:
    """失败次数超过阈值时锁定，Redis 不可用则拒绝身份核验。"""
    redis = get_redis()
    key = _verify_rate_key(request, task_no)
    try:
        count = int(redis.client.incr(key))
        if count == 1:
            redis.client.expire(key, VERIFY_WINDOW_SECONDS)
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCode.ERR_PATIENT_004, "身份核验服务暂不可用", http_status=503) from exc
    if count > VERIFY_LIMIT:
        logger.warning(
            "患者任务身份核验触发限流: task_no=%s client=%s",
            task_no,
            request.client.host if request.client else "unknown",
        )
        raise AppError(ErrorCode.ERR_PATIENT_007)
    return key


def verify_task_identity(
    db: Session,
    request: Request,
    *,
    task_no: str,
    id_card_suffix: str,
) -> tuple[Patient, PatientEncounter, CareTask, str]:
    """用任务编号和身份证后四位登录患者端。"""
    rate_key = _check_verify_limit(request, task_no)
    task, patient, encounter = _task_by_no(db, task_no)
    identity = decrypt_id_card(
        patient.id_card_ciphertext,
        get_app_config().security.patient_identity_secret,
    )
    if not identity or normalize_id_card(identity)[-4:] != normalize_id_card(id_card_suffix):
        logger.warning(
            "患者任务身份核验失败: task_no=%s client=%s",
            task_no,
            request.client.host if request.client else "unknown",
        )
        raise AppError(ErrorCode.ERR_PATIENT_001)
    get_redis().delete(rate_key)
    token = patient_service.create_patient_session(
        patient_id=patient.id,
        encounter_id=encounter.id,
    )
    logger.info(
        "患者任务身份核验成功: task_no=%s patient_id=%s encounter_id=%s",
        task.task_no,
        patient.id,
        encounter.id,
    )
    return patient, encounter, task, token


def create_scan_token(
    db: Session,
    *,
    task_no: str,
    expires_in_seconds: int,
) -> dict[str, Any]:
    """创建一次性扫码令牌。

    令牌只保存 SHA-256 摘要，Redis 取出后原子删除；响应不包含患者资料。
    """
    task, _, encounter = _task_by_no(db, task_no)
    raw = secrets.token_urlsafe(36)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = _now() + timedelta(seconds=expires_in_seconds)
    saved = get_redis().set(
        f"{SCAN_TOKEN_PREFIX}{digest}",
        {"task_id": task.id, "encounter_id": encounter.id},
        ex=expires_in_seconds,
    )
    if not saved:
        raise AppError(ErrorCode.ERR_PATIENT_004, "扫码服务暂不可用", http_status=503)
    return {
        "token": raw,
        "task_no": task.task_no,
        "expires_at": expires_at,
        "expires_in_seconds": expires_in_seconds,
    }


def consume_scan_token(
    db: Session,
    token: str,
) -> tuple[Patient, PatientEncounter, CareTask, str]:
    """消费一次性扫码令牌并创建患者会话。"""
    digest = hashlib.sha256(token.encode()).hexdigest()
    payload = get_redis().get_and_delete(f"{SCAN_TOKEN_PREFIX}{digest}")
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.ERR_PATIENT_008)
    task = db.get(CareTask, payload.get("task_id"))
    encounter = db.get(PatientEncounter, payload.get("encounter_id"))
    if task is None or encounter is None or encounter.encounter_status != "在院":
        raise AppError(ErrorCode.ERR_PATIENT_008)
    patient = db.get(Patient, task.patient_id)
    if patient is None or task.encounter_id != encounter.id or patient.deleted or task.deleted:
        raise AppError(ErrorCode.ERR_PATIENT_008)
    session_token = patient_service.create_patient_session(
        patient_id=patient.id,
        encounter_id=encounter.id,
    )
    return patient, encounter, task, session_token


def list_notifications(
    db: Session,
    *,
    patient_id: int,
    encounter_id: int,
    unread_only: bool = False,
) -> tuple[list[PatientNotificationDto], int]:
    """查询当前住院记录通知并返回未读数。"""
    now = _now()
    statement = select(PatientNotification).where(
        PatientNotification.patient_id == patient_id,
        PatientNotification.deleted == 0,
        or_(
            PatientNotification.expires_at.is_(None),
            PatientNotification.expires_at > now,
        ),
        or_(
            PatientNotification.encounter_id == encounter_id,
            PatientNotification.encounter_id.is_(None),
        ),
    )
    if unread_only:
        statement = statement.where(PatientNotification.read_at.is_(None))
    rows = list(
        db.scalars(statement.order_by(PatientNotification.create_time.desc())).all()
    )
    from sqlalchemy import func
    unread = int(
        db.scalar(
            select(func.count(PatientNotification.id)).where(
                PatientNotification.patient_id == patient_id,
                PatientNotification.deleted == 0,
                or_(
                    PatientNotification.expires_at.is_(None),
                    PatientNotification.expires_at > now,
                ),
                or_(
                    PatientNotification.encounter_id == encounter_id,
                    PatientNotification.encounter_id.is_(None),
                ),
                PatientNotification.read_at.is_(None),
            )
        )
        or 0
    )
    return [
        PatientNotificationDto(
            id=row.id,
            notification_no=row.notification_no,
            notification_type=row.notification_type,
            title=row.title,
            content=row.content,
            priority=row.priority,
            payload=row.payload or {},
            read_at=row.read_at,
            created_at=row.create_time,
        )
        for row in rows
    ], unread


def mark_notification_read(
    db: Session,
    *,
    patient_id: int,
    encounter_id: int,
    notification_id: int,
) -> PatientNotificationDto:
    """幂等标记通知已读。"""
    row = db.scalar(
        select(PatientNotification).where(
            PatientNotification.id == notification_id,
            PatientNotification.patient_id == patient_id,
            PatientNotification.deleted == 0,
            or_(
                PatientNotification.expires_at.is_(None),
                PatientNotification.expires_at > _now(),
            ),
            or_(
                PatientNotification.encounter_id == encounter_id,
                PatientNotification.encounter_id.is_(None),
            ),
        )
    )
    if row is None:
        raise AppError(ErrorCode.ERR_COMMON_002, "通知不存在", http_status=404)
    row.read_at = row.read_at or _now()
    db.commit()
    return PatientNotificationDto(
        id=row.id,
        notification_no=row.notification_no,
        notification_type=row.notification_type,
        title=row.title,
        content=row.content,
        priority=row.priority,
        payload=row.payload or {},
        read_at=row.read_at,
        created_at=row.create_time,
    )


def list_ward_guides(
    db: Session,
    *,
    department_code: str | None,
    department_name: str | None,
    ward_name: str | None,
) -> list[WardGuideDto]:
    """返回当前病区和科室的已发布指南。"""
    statement = select(WardGuide).where(
        WardGuide.status == "published",
        WardGuide.deleted == 0,
        or_(
            WardGuide.department_code.is_(None),
            WardGuide.department_code == department_code,
        ),
        or_(
            WardGuide.department_name.is_(None),
            WardGuide.department_name == department_name,
        ),
        or_(WardGuide.ward_name.is_(None), WardGuide.ward_name == ward_name),
    )
    rows = db.scalars(statement.order_by(WardGuide.sort_no, WardGuide.id)).all()
    return [
        WardGuideDto(
            id=row.id,
            guide_code=row.guide_code,
            category=row.category,
            title=row.title,
            content=row.content,
            department_name=row.department_name,
            ward_name=row.ward_name,
            sort_no=row.sort_no,
        )
        for row in rows
    ]


def _assistant_dto(db: Session, session: PatientAssistantSession) -> PatientAssistantSessionDto:
    messages = db.scalars(
        select(PatientAssistantMessage)
        .where(
            PatientAssistantMessage.session_id == session.id,
            PatientAssistantMessage.deleted == 0,
        )
        .order_by(PatientAssistantMessage.occurred_at, PatientAssistantMessage.id)
    ).all()
    return PatientAssistantSessionDto(
        session_no=session.session_no,
        channel_type=session.channel_type,
        session_status=session.session_status,
        handoff_required=session.handoff_required,
        handoff_reason=session.handoff_reason,
        messages=[
            PatientAssistantMessageDto(
                message_no=item.message_no,
                role=item.role_type,  # type: ignore[arg-type]
                content=item.content_text,
                result_status=item.result_status,
                source_guide_id=item.source_guide_id,
                occurred_at=item.occurred_at,
            )
            for item in messages
        ],
    )


def create_assistant_session(
    db: Session,
    *,
    patient_id: int,
    encounter_id: int,
    channel_type: str,
) -> PatientAssistantSessionDto:
    """创建独立助手会话。"""
    session = PatientAssistantSession(
        session_no=f"PA-{uuid.uuid4().hex.upper()}",
        patient_id=patient_id,
        encounter_id=encounter_id,
        channel_type=channel_type,
        session_status="active",
        creator="patient",
        updator="patient",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _assistant_dto(db, session)


def get_assistant_session(
    db: Session,
    *,
    patient_id: int,
    encounter_id: int,
    session_no: str,
) -> PatientAssistantSessionDto:
    """读取当前患者的助手历史。"""
    session = db.scalar(
        select(PatientAssistantSession).where(
            PatientAssistantSession.session_no == session_no,
            PatientAssistantSession.patient_id == patient_id,
            PatientAssistantSession.encounter_id == encounter_id,
            PatientAssistantSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_COMMON_002, "助手会话不存在", http_status=404)
    return _assistant_dto(db, session)


def send_assistant_message(
    db: Session,
    *,
    patient_id: int,
    encounter_id: int,
    session_no: str,
    content: str,
    client_message_id: str | None,
) -> PatientAssistantSessionDto:
    """回答住院生活问题，超出指南范围时明确转护士。"""
    normalized = content.strip()
    if not normalized:
        raise AppError(ErrorCode.ERR_COMMON_001, "问题内容不能为空")
    session = db.scalar(
        select(PatientAssistantSession).where(
            PatientAssistantSession.session_no == session_no,
            PatientAssistantSession.patient_id == patient_id,
            PatientAssistantSession.encounter_id == encounter_id,
            PatientAssistantSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_COMMON_002, "助手会话不存在", http_status=404)
    if client_message_id:
        patient_message_no = _patient_assistant_message_no(client_message_id)
        existing = db.scalar(
            select(PatientAssistantMessage).where(
                PatientAssistantMessage.session_id == session.id,
                PatientAssistantMessage.message_no == patient_message_no,
                PatientAssistantMessage.deleted == 0,
            )
        )
        if existing is not None:
            return _assistant_dto(db, session)

    now = _now()
    patient_message = PatientAssistantMessage(
        session_id=session.id,
        message_no=_patient_assistant_message_no(client_message_id),
        role_type="patient",
        content_text=normalized,
        occurred_at=now,
        creator="patient",
        updator="patient",
    )
    db.add(patient_message)
    department_code, ward_name = _encounter_department(db, encounter_id)
    guides = list(
        db.scalars(
            select(WardGuide).where(
                WardGuide.status == "published",
                WardGuide.deleted == 0,
                or_(
                    WardGuide.department_code.is_(None),
                    WardGuide.department_code == department_code,
                ),
                or_(
                    WardGuide.ward_name.is_(None),
                    WardGuide.ward_name == ward_name,
                ),
            )
        ).all()
    )
    normalized = normalized.lower()
    matched = next(
        (
            guide
            for guide in guides
            if any(str(keyword).lower() in normalized for keyword in (guide.keywords or []))
            or guide.title.lower() in normalized
        ),
        None,
    )
    if matched is None:
        answer = "这个问题需要护士结合您的具体情况回答，我已为您标记并建议联系护士。"
        result_status = "handoff_required"
        session.handoff_required = True
        session.handoff_reason = "住院助手问题超出当前病区指南范围"
    else:
        answer = matched.content
        result_status = "answered"
    db.add(
        PatientAssistantMessage(
            session_id=session.id,
            message_no=f"ASSISTANT-{uuid.uuid4().hex.upper()}",
            role_type="assistant",
            content_text=answer,
            result_status=result_status,
            source_guide_id=matched.id if matched else None,
            occurred_at=now,
            creator="patient_assistant",
            updator="patient_assistant",
        )
    )
    session.last_message_at = now
    db.commit()
    db.refresh(session)
    return _assistant_dto(db, session)


def _encounter_department(db: Session, encounter_id: int) -> tuple[str | None, str | None]:
    encounter = db.get(PatientEncounter, encounter_id)
    return (
        encounter.department_code if encounter else None,
        encounter.ward_name if encounter else None,
    )


def _patient_assistant_message_no(client_message_id: str | None) -> str:
    """生成不超过数据库 64 字符且可稳定幂等的患者消息编号。"""
    if client_message_id:
        digest = hashlib.sha256(client_message_id.encode("utf-8")).hexdigest()
        return f"PATIENT-{digest[:56]}"
    return f"PATIENT-{uuid.uuid4().hex.upper()}"


def _consent_context(
    db: Session,
    *,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
) -> tuple[CareTask, ConsentRecord, ConsentDocument, ConsentDocumentVersion, list[ConsentClause]]:
    task = _task_for_patient(db, task_ref, patient_id, encounter_id)
    record = db.scalar(
        select(ConsentRecord).where(
            ConsentRecord.task_id == task.id,
            ConsentRecord.patient_id == patient_id,
            ConsentRecord.deleted == 0,
        )
    )
    if record is None:
        now = _now()
        version = db.scalar(
            select(ConsentDocumentVersion)
            .join(ConsentDocument, ConsentDocument.id == ConsentDocumentVersion.consent_document_id)
            .where(
                ConsentDocument.status == "active",
                ConsentDocumentVersion.publish_status == "published",
                ConsentDocumentVersion.deleted == 0,
                ConsentDocument.deleted == 0,
                or_(
                    ConsentDocumentVersion.effective_time.is_(None),
                    ConsentDocumentVersion.effective_time <= now,
                ),
                or_(
                    ConsentDocumentVersion.expire_time.is_(None),
                    ConsentDocumentVersion.expire_time > now,
                ),
            )
            .order_by(ConsentDocumentVersion.effective_time.desc().nullslast(), ConsentDocumentVersion.id.desc())
        )
        if version is None:
            raise AppError(ErrorCode.ERR_PATIENT_009)
        record = ConsentRecord(
            task_id=task.id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            consent_document_id=version.consent_document_id,
            consent_version_id=version.id,
            participant_type="patient",
            record_status="进行中",
            started_at=_now(),
            creator="patient",
            updator="patient",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    document = db.get(ConsentDocument, record.consent_document_id)
    version = db.get(ConsentDocumentVersion, record.consent_version_id)
    if document is None or version is None:
        raise AppError(ErrorCode.ERR_PATIENT_009)
    clauses = list(
        db.scalars(
            select(ConsentClause)
            .where(
                ConsentClause.consent_version_id == version.id,
                ConsentClause.deleted == 0,
            )
            .order_by(ConsentClause.sort_no, ConsentClause.id)
        ).all()
    )
    return task, record, document, version, clauses


def get_consent_snapshot(
    db: Session,
    *,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
) -> dict[str, Any]:
    """返回任务绑定的条款、确认、参与人、签名和播放进度。"""
    task, record, document, version, clauses = _consent_context(
        db, task_ref=task_ref, patient_id=patient_id, encounter_id=encounter_id
    )
    confirmations = db.scalars(
        select(ConsentClauseRecord).where(
            ConsentClauseRecord.consent_record_id == record.id,
            ConsentClauseRecord.deleted == 0,
        )
    ).all()
    participants = db.scalars(
        select(ConsentParticipant).where(
            ConsentParticipant.consent_record_id == record.id,
            ConsentParticipant.deleted == 0,
        )
    ).all()
    signatures = db.scalars(
        select(ConsentSignature).where(
            ConsentSignature.consent_record_id == record.id,
            ConsentSignature.deleted == 0,
        )
    ).all()
    items = db.scalars(
        select(ContentDeliveryItem)
        .join(ContentDeliverySession, ContentDeliverySession.id == ContentDeliveryItem.delivery_session_id)
        .where(
            ContentDeliverySession.business_type == "consent",
            ContentDeliverySession.business_id == record.id,
            ContentDeliveryItem.deleted == 0,
        )
    ).all()
    return {
        "task_no": task.task_no,
        "record_id": record.id,
        "consent_code": document.consent_code,
        "consent_name": document.consent_name,
        "consent_type": document.consent_type,
        "document_version": version.version_code,
        "full_text": version.full_text,
        "record_status": record.record_status,
        "patient_confirmed": record.patient_confirmed,
        "participant_type": record.participant_type,
        "clauses": [
            {
                "id": clause.id,
                "clause_code": clause.clause_code,
                "title": clause.clause_title,
                "original_content": clause.original_content,
                "patient_content": clause.patient_content,
                "voice_content": clause.voice_content,
                "audio_url": clause.audio_url,
                "audio_duration_seconds": clause.audio_duration_seconds,
                "importance_level": clause.importance_level,
                "confirmation_required": clause.confirmation_required,
                "teachback_required": clause.teachback_required,
                "sort_no": clause.sort_no,
            }
            for clause in clauses
        ],
        "confirmations": [
            {
                "clause_id": item.clause_id,
                "confirmation_result": item.confirmation_result,
                "patient_reply": item.patient_reply,
                "confirmed_at": item.confirmed_at.isoformat() if item.confirmed_at else None,
                "need_nurse_explain": item.need_nurse_explain,
            }
            for item in confirmations
        ],
        "playback": [
            {
                "clause_id": item.source_id,
                "position_seconds": item.position_seconds,
                "playback_status": item.playback_status,
                "patient_acknowledged": item.patient_acknowledged,
            }
            for item in items
        ],
        "participants": [
            {
                "id": participant.id,
                "participant_type": participant.participant_type,
                "participant_name": participant.participant_name,
                "relationship_to_patient": participant.relationship_to_patient,
                "confirmed_at": participant.confirmed_at.isoformat() if participant.confirmed_at else None,
            }
            for participant in participants
        ],
        "signatures": [
            {
                "id": signature.id,
                "participant_id": signature.participant_id,
                "signer_type": signature.signer_type,
                "signer_name_snapshot": signature.signer_name_snapshot,
                "signature_method": signature.signature_method,
                "signature_file_url": signature.signature_file_url,
                "signed_at": signature.signed_at.isoformat(),
            }
            for signature in signatures
        ],
    }


def _delivery_item(
    db: Session,
    *,
    record: ConsentRecord,
    clause: ConsentClause,
) -> ContentDeliveryItem:
    session = db.scalar(
        select(ContentDeliverySession).where(
            ContentDeliverySession.business_type == "consent",
            ContentDeliverySession.business_id == record.id,
            ContentDeliverySession.deleted == 0,
        )
    )
    if session is None:
        session = ContentDeliverySession(
            patient_id=record.patient_id,
            encounter_id=record.encounter_id,
            business_type="consent",
            business_id=record.id,
            channel_type="voice",
            status="in_progress",
            started_at=_now(),
            creator="patient",
            updator="patient",
        )
        db.add(session)
        db.flush()
    item = db.scalar(
        select(ContentDeliveryItem).where(
            ContentDeliveryItem.delivery_session_id == session.id,
            ContentDeliveryItem.source_id == clause.id,
            ContentDeliveryItem.deleted == 0,
        )
    )
    if item is None:
        item = ContentDeliveryItem(
            delivery_session_id=session.id,
            item_type="consent_clause",
            source_id=clause.id,
            original_text_snapshot=clause.original_content,
            patient_text_snapshot=clause.patient_content,
            voice_text_snapshot=clause.voice_content,
            audio_url=clause.audio_url,
            audio_duration_seconds=clause.audio_duration_seconds,
            creator="patient",
            updator="patient",
        )
        db.add(item)
        db.flush()
    return item


def record_consent_playback(
    db: Session,
    *,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
    request: ConsentPlaybackRequest,
) -> dict[str, Any]:
    """保存播放进度并支持调用编号幂等。"""
    _, record, _, _, clauses = _consent_context(
        db, task_ref=task_ref, patient_id=patient_id, encounter_id=encounter_id
    )
    clause = next((item for item in clauses if item.id == request.clause_id), None)
    if clause is None:
        raise AppError(ErrorCode.ERR_COMMON_002, "知情同意条款不存在", http_status=404)
    item = _delivery_item(db, record=record, clause=clause)
    if request.client_invocation_id:
        existing = db.scalar(
            select(ContentPlaybackEvent).where(
                ContentPlaybackEvent.delivery_item_id == item.id,
                ContentPlaybackEvent.client_invocation_id == request.client_invocation_id,
                ContentPlaybackEvent.deleted == 0,
            )
        )
        if existing is not None:
            return {"item_id": item.id, "position_seconds": item.position_seconds, "playback_status": item.playback_status}
    status = {
        "start": "playing",
        "pause": "paused",
        "resume": "playing",
        "complete": "completed",
        "replay": "playing",
    }[request.event_type]
    item.position_seconds = request.position_seconds
    item.playback_status = status
    if request.event_type == "complete":
        item.patient_acknowledged = True
    db.add(
        ContentPlaybackEvent(
            delivery_item_id=item.id,
            event_type=request.event_type,
            position_seconds=request.position_seconds,
            client_invocation_id=request.client_invocation_id,
            occurred_at=_now(),
            creator="patient",
            updator="patient",
        )
    )
    db.commit()
    return {"item_id": item.id, "clause_id": clause.id, "position_seconds": item.position_seconds, "playback_status": item.playback_status, "patient_acknowledged": item.patient_acknowledged}


def confirm_consent_clause(
    db: Session,
    *,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
    clause_id: int,
    request: ConsentClauseConfirmRequest,
) -> dict[str, Any]:
    """幂等保存条款确认结果，并更新总体记录状态。"""
    _, record, _, _, clauses = _consent_context(
        db, task_ref=task_ref, patient_id=patient_id, encounter_id=encounter_id
    )
    if not any(item.id == clause_id for item in clauses):
        raise AppError(ErrorCode.ERR_COMMON_002, "知情同意条款不存在", http_status=404)
    row = db.scalar(
        select(ConsentClauseRecord).where(
            ConsentClauseRecord.consent_record_id == record.id,
            ConsentClauseRecord.clause_id == clause_id,
            ConsentClauseRecord.deleted == 0,
        )
    )
    if row is None:
        row = ConsentClauseRecord(
            consent_record_id=record.id,
            clause_id=clause_id,
            confirmation_result=request.confirmation_result,
            patient_reply=request.patient_reply,
            confirmed_at=_now(),
            need_nurse_explain=request.confirmation_result in {"未理解", "不确定", "拒绝"},
            creator="patient",
            updator="patient",
        )
        db.add(row)
    else:
        row.confirmation_result = request.confirmation_result
        row.patient_reply = request.patient_reply
        row.confirmed_at = _now()
        row.need_nurse_explain = request.confirmation_result in {"未理解", "不确定", "拒绝"}
    all_required = [item for item in clauses if item.confirmation_required]
    confirmed = {
        item.clause_id: item
        for item in db.scalars(
            select(ConsentClauseRecord).where(
                ConsentClauseRecord.consent_record_id == record.id,
                ConsentClauseRecord.deleted == 0,
            )
        ).all()
    }
    confirmed[clause_id] = row
    if any(item.need_nurse_explain for item in confirmed.values()):
        record.record_status = "需护士解释"
    elif all(item.id in confirmed and confirmed[item.id].confirmation_result == "已理解并确认" for item in all_required):
        record.record_status = "已完成"
        record.patient_confirmed = True
        record.completed_at = _now()
    db.commit()
    return {
        "record_id": record.id,
        "clause_id": clause_id,
        "confirmation_result": row.confirmation_result,
        "record_status": record.record_status,
        "patient_confirmed": record.patient_confirmed,
    }


def save_consent_participant(
    db: Session,
    *,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
    participant_type: str,
    participant_name: str,
    relationship_to_patient: str | None,
) -> dict[str, Any]:
    """保存/复用患者或家属参与人快照。"""
    _, record, _, _, _ = _consent_context(
        db, task_ref=task_ref, patient_id=patient_id, encounter_id=encounter_id
    )
    row = db.scalar(
        select(ConsentParticipant).where(
            ConsentParticipant.consent_record_id == record.id,
            ConsentParticipant.participant_type == participant_type,
            ConsentParticipant.participant_name == participant_name,
            ConsentParticipant.deleted == 0,
        )
    )
    if row is None:
        row = ConsentParticipant(
            consent_record_id=record.id,
            participant_type=participant_type,
            participant_name=participant_name,
            relationship_to_patient=relationship_to_patient,
            confirmed_at=_now(),
            creator="patient",
            updator="patient",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"id": row.id, "participant_type": row.participant_type, "participant_name": row.participant_name, "relationship_to_patient": row.relationship_to_patient}


def attach_consent_signature(
    db: Session,
    *,
    task_ref: str | int,
    patient_id: int,
    encounter_id: int,
    participant_name: str,
    participant_type: str,
    signature_file_url: str | None,
    signed_content_hash: str | None,
    signature_method: str = "手写签名",
) -> dict[str, Any]:
    """把既有受保护签名文件挂接到结构化同意记录。"""
    _, record, _, _, _ = _consent_context(
        db, task_ref=task_ref, patient_id=patient_id, encounter_id=encounter_id
    )
    participant = save_consent_participant(
        db,
        task_ref=task_ref,
        patient_id=patient_id,
        encounter_id=encounter_id,
        participant_type=participant_type,
        participant_name=participant_name,
        relationship_to_patient=None,
    )
    row = db.scalar(
        select(ConsentSignature).where(
            ConsentSignature.consent_record_id == record.id,
            ConsentSignature.signer_name_snapshot == participant_name,
            ConsentSignature.deleted == 0,
        )
    )
    if row is None:
        row = ConsentSignature(
            consent_record_id=record.id,
            participant_id=participant["id"],
            signer_type=participant_type,
            signer_name_snapshot=participant_name,
            signature_method=signature_method,
            signature_file_url=signature_file_url,
            signed_content_hash=signed_content_hash,
            signed_at=_now(),
            creator="patient",
            updator="patient",
        )
        db.add(row)
    else:
        row.signature_file_url = signature_file_url
        row.signed_content_hash = signed_content_hash
        row.signed_at = _now()
    db.commit()
    db.refresh(row)
    return {"id": row.id, "record_id": record.id, "signature_file_url": row.signature_file_url, "signed_at": row.signed_at}
