"""患者服务
作用：封装患者与住院记录的查询逻辑。
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.patient_task import Patient, PatientEncounter
from app.schemas.patient import (
    InHospitalPatientDto,
    PatientDto,
    PatientEncounterDto,
    PatientLoginRequest,
    PatientLoginResponse,
)
from app.services import task_service
from app.utils.patient_identity import normalize_phone, verify_id_card
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)
SESSION_KEY_PREFIX = "patient_auth:"


def list_in_hospital_patients(db: Session) -> list[InHospitalPatientDto]:
    """查询在院患者列表
    作用：返回 encounter_status="在院" 的患者及其住院记录，供前端患者列表使用。
    Args:
        - db: 数据库会话
    Return:
        - InHospitalPatientDto 列表
    """
    rows = list(
        db.execute(
            select(Patient, PatientEncounter)
            .join(PatientEncounter, PatientEncounter.patient_id == Patient.id)
            .where(
                Patient.deleted == 0,
                PatientEncounter.encounter_status == "在院",
                PatientEncounter.deleted == 0,
            )
            .order_by(PatientEncounter.admission_time.desc())
        ).all()
    )

    result = []
    for patient, enc in rows:
        result.append(
            InHospitalPatientDto(
                patient=PatientDto(
                    id=patient.id,
                    patient_no=patient.patient_no,
                    patient_name=patient.patient_name,
                    sex=patient.sex,
                    birthday=patient.birthday,
                    phone=patient.phone,
                ),
                encounter=PatientEncounterDto(
                    id=enc.id,
                    encounter_no=enc.encounter_no,
                    inpatient_no=enc.inpatient_no,
                    patient_id=enc.patient_id,
                    department_code=enc.department_code,
                    department_name=enc.department_name,
                    ward_name=enc.ward_name,
                    bed_no=enc.bed_no,
                    admission_time=enc.admission_time,
                    encounter_status=enc.encounter_status,
                    diagnosis_snapshot=enc.diagnosis_snapshot,
                ),
            )
        )

    logger.info(f"查询在院患者: 共 {len(result)} 条")
    return result


def _session_key(token: str) -> str:
    """生成患者会话 Redis Key。"""
    return f"{SESSION_KEY_PREFIX}{token}"


def _patient_dto(patient: Patient) -> PatientDto:
    """转换患者 DTO，不返回身份证号。"""
    return PatientDto(
        id=patient.id,
        patient_no=patient.patient_no,
        patient_name=patient.patient_name,
        sex=patient.sex,
        birthday=patient.birthday,
        phone=patient.phone,
    )


def _encounter_dto(encounter: PatientEncounter) -> PatientEncounterDto:
    """转换住院记录 DTO。"""
    return PatientEncounterDto(
        id=encounter.id,
        encounter_no=encounter.encounter_no,
        inpatient_no=encounter.inpatient_no,
        patient_id=encounter.patient_id,
        department_code=encounter.department_code,
        department_name=encounter.department_name,
        ward_name=encounter.ward_name,
        bed_no=encounter.bed_no,
        admission_time=encounter.admission_time,
        encounter_status=encounter.encounter_status,
        diagnosis_snapshot=encounter.diagnosis_snapshot,
    )


def _active_encounter(db: Session, patient_id: int) -> PatientEncounter | None:
    """查询患者当前在院记录。"""
    return db.scalar(
        select(PatientEncounter)
        .where(
            PatientEncounter.patient_id == patient_id,
            PatientEncounter.encounter_status == "在院",
            PatientEncounter.deleted == 0,
        )
        .order_by(PatientEncounter.admission_time.desc(), PatientEncounter.id.desc())
    )


def login_patient(
    db: Session,
    request: PatientLoginRequest,
) -> tuple[PatientLoginResponse, str]:
    """核验住院患者身份并创建患者端登录会话。"""
    phone = normalize_phone(request.phone)
    candidates = db.scalars(
        select(Patient).where(
            Patient.deleted == 0,
            func.replace(Patient.phone, " ", "") == phone,
        )
    ).all()
    patient = next(
        (
            item
            for item in candidates
            if verify_id_card(
                request.id_card_no,
                item.id_card_ciphertext,
                get_app_config().security.patient_identity_secret,
            )
        ),
        None,
    )
    if patient is None:
        raise AppError(ErrorCode.ERR_PATIENT_001)

    encounter = _active_encounter(db, patient.id)
    if encounter is None:
        raise AppError(ErrorCode.ERR_PATIENT_002)

    token = secrets.token_urlsafe(32)
    config = get_app_config()
    session_saved = get_redis().set(
        _session_key(token),
        {
            "patient_id": patient.id,
            "encounter_id": encounter.id,
        },
        ex=config.security.patient_session_ttl_seconds,
    )
    if not session_saved:
        raise AppError(ErrorCode.ERR_PATIENT_004)

    return (
        PatientLoginResponse(
            patient=_patient_dto(patient),
            encounter=_encounter_dto(encounter),
            tasks=task_service.list_patient_tasks(
                db,
                patient_id=patient.id,
                encounter_id=encounter.id,
            ),
        ),
        token,
    )


def get_patient_context(
    db: Session,
    request: Request,
) -> tuple[Patient, PatientEncounter]:
    """读取当前患者登录会话并校验住院状态。"""
    cookie_name = get_app_config().security.patient_session_cookie
    token = request.cookies.get(cookie_name)
    if not token:
        raise AppError(ErrorCode.ERR_PATIENT_003)

    payload: Any = get_redis().get(_session_key(token))
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.ERR_PATIENT_003)

    patient = db.scalar(
        select(Patient).where(
            Patient.id == payload.get("patient_id"),
            Patient.deleted == 0,
        )
    )
    encounter = db.scalar(
        select(PatientEncounter).where(
            PatientEncounter.id == payload.get("encounter_id"),
            PatientEncounter.patient_id == payload.get("patient_id"),
            PatientEncounter.encounter_status == "在院",
            PatientEncounter.deleted == 0,
        )
    )
    if patient is None or encounter is None:
        raise AppError(ErrorCode.ERR_PATIENT_003)
    return patient, encounter


def get_patient_portal(
    db: Session,
    request: Request,
) -> PatientLoginResponse:
    """返回当前登录患者的住院信息和本人任务。"""
    patient, encounter = get_patient_context(db, request)
    return PatientLoginResponse(
        patient=_patient_dto(patient),
        encounter=_encounter_dto(encounter),
        tasks=task_service.list_patient_tasks(
            db,
            patient_id=patient.id,
            encounter_id=encounter.id,
        ),
    )


def logout_patient(request: Request) -> None:
    """删除当前患者登录会话。"""
    cookie_name = get_app_config().security.patient_session_cookie
    token = request.cookies.get(cookie_name)
    if token:
        get_redis().delete(_session_key(token))
