"""知情同意接口
作用：接收患者在对话内完成的条款确认与手写签名。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_patient, require_staff_or_patient
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.base import get_db
from app.models.interaction import InteractionEvent, InteractionSession
from app.models.patient_task import Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.schemas.interaction_tools import ConsentSignRequest
from app.schemas.response import ApiResponse, ok
from app.services import tool_interaction_service

router = APIRouter(prefix="/api/consent-forms", tags=["consent"])
DbSession = Annotated[Session, Depends(get_db)]
_SIGNATURE_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "storage" / "consent-signatures"
)
_SAFE_SIGNATURE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@router.post(
    "/{task_ref}/sign",
    response_model=ApiResponse[dict],
    summary="提交患者知情同意决定和签名",
)
def sign_consent(
    task_ref: str,
    req: ConsentSignRequest,
    db: DbSession,
    patient_context: Annotated[
        tuple[Patient, PatientEncounter],
        Depends(require_patient),
    ],
) -> dict:
    """保存签名文件、内容摘要和签署状态。"""
    patient, _ = patient_context
    return ok(
        tool_interaction_service.submit_consent(
            db,
            task_ref,
            req,
            patient_id=patient.id,
        )
    )


@router.get(
    "/signatures/{filename}",
    summary="读取受保护的知情同意签名",
)
def get_consent_signature(
    filename: str,
    db: DbSession,
    actor: Annotated[
        StaffAccount | tuple[Patient, PatientEncounter],
        Depends(require_staff_or_patient),
    ],
):
    """仅允许相关患者或已登录医护读取签名文件。"""
    if _SAFE_SIGNATURE_NAME.fullmatch(filename) is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "签名文件名无效", http_status=404)

    signature_url = f"/api/consent-forms/signatures/{filename}"
    events = db.scalars(
        select(InteractionEvent)
        .join(
            InteractionSession,
            InteractionSession.id == InteractionEvent.interaction_session_id,
        )
        .where(
            InteractionEvent.event_type == "consent_status_updated",
            InteractionEvent.deleted == 0,
            InteractionSession.deleted == 0,
        )
    ).all()

    for event in events:
        if event.event_payload.get("signature_file_url") != signature_url:
            continue
        if isinstance(actor, tuple):
            session = db.get(InteractionSession, event.interaction_session_id)
            if session is None or session.patient_id != actor[0].id:
                continue
        path = (_SIGNATURE_DIRECTORY / filename).resolve()
        if _SIGNATURE_DIRECTORY.resolve() not in path.parents or not path.is_file():
            break
        media_type = "image/jpeg" if filename.lower().endswith(".jpg") else "image/png"
        return FileResponse(path, media_type=media_type)

    raise AppError(ErrorCode.ERR_COMMON_001, "签名文件不存在", http_status=404)
