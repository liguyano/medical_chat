"""知情同意接口
作用：接收患者在对话内完成的条款确认与手写签名。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_patient
from app.models.base import get_db
from app.models.patient_task import Patient, PatientEncounter
from app.schemas.interaction_tools import ConsentSignRequest
from app.schemas.response import ApiResponse, ok
from app.services import tool_interaction_service

router = APIRouter(prefix="/api/consent-forms", tags=["consent"])
DbSession = Annotated[Session, Depends(get_db)]


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
