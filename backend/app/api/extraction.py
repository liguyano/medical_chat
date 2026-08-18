"""字段抽取路由
作用：提供抽取字段查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_staff_or_patient
from app.models.base import get_db
from app.models.patient_task import Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.schemas.extraction import ExtractedFieldsResponse
from app.schemas.response import ApiResponse, ok
from app.services import extraction_service

router = APIRouter(prefix="/api/extraction", tags=["extraction"])


@router.get(
    "/{session_no}/fields",
    response_model=ApiResponse[ExtractedFieldsResponse],
    summary="查询会话抽取字段",
)
def get_extracted_fields(
    session_no: str,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[
        StaffAccount | tuple[Patient, PatientEncounter],
        Depends(require_staff_or_patient),
    ],
) -> dict:
    """查询会话抽取字段
    作用：返回指定会话的 AI 抽取结果（字段列表）。
    Args:
        - session_no: 会话编号
        - db: 数据库会话
    Return:
        - 抽取字段响应（含 session_id 与 fields 列表）
    """
    patient_id = actor[0].id if isinstance(actor, tuple) else None
    return ok(
        extraction_service.get_extracted_fields(
            db,
            session_no,
            patient_id=patient_id,
        )
    )
