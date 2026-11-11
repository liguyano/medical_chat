"""设备登记、在线状态和任务绑定查询。"""

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models import base
from app.models.device_registration import DeviceRegistration
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask


def heartbeat_key(device_id: str) -> str:
    return f"device_http:online:{device_id}"


def registered_devices():
    raw = os.getenv("DEVICE_HTTP_CREDENTIALS") or os.getenv("DEVICE_TCP_CREDENTIALS") or "{}"
    devices = json.loads(raw)
    if not isinstance(devices, dict) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
        for device_id, digest in devices.items()
    ):
        raise ValueError("DEVICE_HTTP_CREDENTIALS 配置无效")
    return devices


def credential_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def approved_digest(db, device_id: str) -> str | None:
    row = db.get(DeviceRegistration, device_id)
    if row is not None:
        return row.secret_digest if row.approved_at is not None else None
    return registered_devices().get(device_id)


def approved_device_ids(db) -> set[str]:
    approved = set(db.scalars(select(DeviceRegistration.device_id).where(
        DeviceRegistration.approved_at.is_not(None)
    )))
    return approved | registered_devices().keys()


def request_registration(db, device_id: str, secret: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id) or not 16 <= len(secret) <= 256:
        raise HTTPException(422, "设备 ID 或密钥长度不符合要求")
    digest = credential_digest(secret)
    legacy = registered_devices().get(device_id)
    if legacy is not None:
        if not hmac.compare_digest(legacy, digest):
            raise HTTPException(409, "设备 ID 已登记")
        return {"status": "approved"}
    now = datetime.now(UTC)
    new_claim = {
        "secret_digest": digest,
        "verification_code": secrets.token_hex(4).upper(),
        "requested_at": now,
        "expires_at": now + timedelta(minutes=15),
    }
    db.execute(insert(DeviceRegistration).values(device_id=device_id, **new_claim)
               .on_conflict_do_nothing(index_elements=["device_id"]))
    row = db.get(DeviceRegistration, device_id, with_for_update=True)
    if row.approved_at is not None:
        if not hmac.compare_digest(row.secret_digest, digest):
            raise HTTPException(409, "设备 ID 已登记")
        return {"status": "approved"}
    if row.expires_at <= now:
        for field, value in new_claim.items():
            setattr(row, field, value)
    elif not hmac.compare_digest(row.secret_digest, digest):
        raise HTTPException(409, "该设备 ID 已有待审批申请")
    result = {
        "status": "pending",
        "verification_code": row.verification_code,
        "expires_at": row.expires_at,
    }
    db.commit()
    return result


def pending_registrations(db) -> list[dict]:
    rows = db.scalars(select(DeviceRegistration).where(
        DeviceRegistration.approved_at.is_(None),
        DeviceRegistration.expires_at > datetime.now(UTC),
    ).order_by(DeviceRegistration.requested_at).limit(100))
    return [{"device_id": row.device_id, "requested_at": row.requested_at} for row in rows]


def approve_registration(db, device_id: str, code: str, *, staff_id: int) -> None:
    row = db.scalar(select(DeviceRegistration).where(
        DeviceRegistration.device_id == device_id
    ).with_for_update())
    if row is None or row.verification_code != code:
        raise HTTPException(409, "核对码不匹配或申请不存在")
    if row.approved_at is not None:
        return
    now = datetime.now(UTC)
    if row.expires_at <= now:
        raise HTTPException(409, "申请已过期，请让设备重新申请")
    row.approved_at = now
    row.approved_by = staff_id
    db.commit()


def check_device_available(db, device_id):
    if approved_digest(db, device_id) is None:
        raise HTTPException(422, "设备未登记")
    if db.scalar(select(CareTask.id).where(
        CareTask.device_id == device_id,
        CareTask.deleted == 0,
        CareTask.task_status.in_(("pending", "in_progress", "pending_review")),
    )) is not None:
        raise HTTPException(409, "设备已有评估任务")


def current_task(device_id):
    with base.SessionLocal() as db:
        return db.execute(
            select(CareTask.task_no, InteractionSession.session_no, CareTask.preparation_status)
            .join(InteractionSession, InteractionSession.task_id == CareTask.id)
            .where(
                CareTask.device_id == device_id,
                CareTask.collection_mode == "embedded_device",
                CareTask.deleted == 0,
                CareTask.task_status == "in_progress",
                InteractionSession.deleted == 0,
                InteractionSession.session_status.in_(("pending", "active")),
            )
            .order_by(InteractionSession.id.desc())
            .limit(1)
        ).first()
