"""设备登记、在线状态和任务绑定查询。"""

import json
import os
import re

from fastapi import HTTPException
from sqlalchemy import select

from app.models import base
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


def check_device_available(db, device_id):
    if device_id not in registered_devices():
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
