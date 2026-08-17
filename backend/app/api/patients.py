"""患者路由
作用：提供在院患者查询接口。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.patient import InHospitalPatientDto
from app.services import patient_service

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get("/in-hospital", summary="查询在院患者列表")
def list_in_hospital_patients(
    db: Session = Depends(get_db),
) -> list[InHospitalPatientDto]:
    """查询在院患者列表
    作用：返回 encounter_status="在院" 的患者及其住院记录。
    Args:
        - db: 数据库会话
    Return:
        - 在院患者列表（患者 + 住院记录）
    """
    return patient_service.list_in_hospital_patients(db)
