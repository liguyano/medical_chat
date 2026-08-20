"""患者服务
作用：封装患者与住院记录的查询逻辑。
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.schemas.patient import (
    InHospitalPatientDto,
    PatientCreateRequest,
    PatientDto,
    PatientEncounterDto,
    PatientLoginRequest,
    PatientLoginResponse,
    PatientRecordDto,
    PatientTaskSummaryDto,
    PatientUpdateRequest,
)
from app.services import task_service
from app.utils.patient_identity import (
    encrypt_id_card,
    mask_id_card,
    normalize_id_card,
    normalize_phone,
    verify_id_card,
)
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)
SESSION_KEY_PREFIX = "patient_auth:"


def _trim(value: str | None) -> str | None:
    """去除可选文本首尾空格，并把空串转换为空值。"""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _session_key(token: str) -> str:
    """生成患者会话 Redis Key。"""
    return f"{SESSION_KEY_PREFIX}{token}"


def _patient_dto(patient: Patient) -> PatientDto:
    """转换患者 DTO，不返回身份证号。"""
    secret = get_app_config().security.patient_identity_secret
    return PatientDto(
        id=patient.id,
        patient_no=patient.patient_no,
        his_patient_id=patient.his_patient_id,
        patient_name=patient.patient_name,
        sex=patient.sex,
        birthday=patient.birthday,
        phone=patient.phone,
        id_card_masked=mask_id_card(patient.id_card_ciphertext, secret),
        emergency_contact_name=patient.emergency_contact_name,
        emergency_contact_relation=patient.emergency_contact_relation,
        emergency_contact_phone=patient.emergency_contact_phone,
        address=patient.address,
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
        discharge_time=encounter.discharge_time,
        encounter_status=encounter.encounter_status,
        diagnosis_snapshot=encounter.diagnosis_snapshot,
        admission_source=encounter.admission_source,
        nursing_level=encounter.nursing_level,
        insurance_type=encounter.insurance_type,
        allergy_summary=encounter.allergy_summary,
    )


def _task_summary(db: Session, encounter_id: int) -> PatientTaskSummaryDto:
    """统计一次住院下的护理任务摘要。"""
    rows = db.execute(
        select(
            CareTask.task_status,
            CareTask.need_manual_intervention,
        ).where(
            CareTask.encounter_id == encounter_id,
            CareTask.deleted == 0,
        )
    ).all()
    return PatientTaskSummaryDto(
        total=len(rows),
        pending_review=sum(1 for status, _ in rows if status == "pending_review"),
        in_progress=sum(1 for status, _ in rows if status == "in_progress"),
        handoff_required=any(bool(required) for _, required in rows),
    )


def _record_dto(
    db: Session,
    patient: Patient,
    encounter: PatientEncounter,
) -> PatientRecordDto:
    """组合患者主档、住院记录和任务摘要。"""
    return PatientRecordDto(
        patient=_patient_dto(patient),
        encounter=_encounter_dto(encounter),
        task_summary=_task_summary(db, encounter.id),
    )


def list_patients(
    db: Session,
    *,
    keyword: str | None = None,
    encounter_status: str | None = None,
    department_name: str | None = None,
    ward_name: str | None = None,
) -> list[PatientRecordDto]:
    """查询医护端患者列表并支持院内常用筛选。"""
    statement = (
        select(Patient, PatientEncounter)
        .join(PatientEncounter, PatientEncounter.patient_id == Patient.id)
        .where(Patient.deleted == 0, PatientEncounter.deleted == 0)
    )
    if encounter_status:
        statement = statement.where(
            PatientEncounter.encounter_status == encounter_status
        )
    if department_name:
        statement = statement.where(
            PatientEncounter.department_name == department_name
        )
    if ward_name:
        statement = statement.where(PatientEncounter.ward_name == ward_name)
    normalized_keyword = _trim(keyword)
    if normalized_keyword:
        pattern = f"%{normalized_keyword}%"
        statement = statement.where(
            or_(
                Patient.patient_name.ilike(pattern),
                Patient.patient_no.ilike(pattern),
                Patient.his_patient_id.ilike(pattern),
                PatientEncounter.inpatient_no.ilike(pattern),
                PatientEncounter.bed_no.ilike(pattern),
            )
        )
    rows = db.execute(
        statement.order_by(
            PatientEncounter.admission_time.desc(),
            PatientEncounter.id.desc(),
        )
    ).all()
    result = [_record_dto(db, patient, encounter) for patient, encounter in rows]
    logger.info("查询患者列表: 共 %s 条", len(result))
    return result


def list_in_hospital_patients(db: Session) -> list[InHospitalPatientDto]:
    """兼容原在院患者列表接口。"""
    return [
        InHospitalPatientDto.model_validate(item.model_dump())
        for item in list_patients(db, encounter_status="在院")
    ]


def get_patient_record(db: Session, patient_id: int) -> PatientRecordDto:
    """查询患者及最近一次住院记录。"""
    row = db.execute(
        select(Patient, PatientEncounter)
        .join(PatientEncounter, PatientEncounter.patient_id == Patient.id)
        .where(
            Patient.id == patient_id,
            Patient.deleted == 0,
            PatientEncounter.deleted == 0,
        )
        .order_by(
            PatientEncounter.admission_time.desc(),
            PatientEncounter.id.desc(),
        )
        .limit(1)
    ).first()
    if row is None:
        raise AppError(ErrorCode.ERR_PATIENT_005)
    return _record_dto(db, row[0], row[1])


def _id_card_owner(
    db: Session,
    id_card_no: str,
    *,
    exclude_patient_id: int | None = None,
) -> Patient | None:
    """扫描加密身份证号并定位已有患者。"""
    secret = get_app_config().security.patient_identity_secret
    candidates = db.scalars(
        select(Patient).where(Patient.deleted == 0)
    ).all()
    return next(
        (
            patient
            for patient in candidates
            if patient.id != exclude_patient_id
            and verify_id_card(id_card_no, patient.id_card_ciphertext, secret)
        ),
        None,
    )


def _new_business_no(db: Session, model: type[Patient] | type[PatientEncounter]) -> str:
    """生成患者或住院过程业务编号。"""
    prefix = "P" if model is Patient else "E"
    field = Patient.patient_no if model is Patient else PatientEncounter.encounter_no
    for _ in range(5):
        value = f"{prefix}-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"
        if db.scalar(select(field).where(field == value)) is None:
            return value
    raise RuntimeError(f"{prefix} 业务编号生成失败")


def _ensure_create_unique(db: Session, request: PatientCreateRequest) -> None:
    """校验患者身份、HIS 编号和住院号不重复。"""
    if _id_card_owner(db, request.patient.id_card_no) is not None:
        raise AppError(ErrorCode.ERR_PATIENT_006, "该身份证号已存在患者主档")
    his_patient_id = _trim(request.patient.his_patient_id)
    if his_patient_id and db.scalar(
        select(Patient.id).where(
            Patient.his_patient_id == his_patient_id,
            Patient.deleted == 0,
        )
    ):
        raise AppError(ErrorCode.ERR_PATIENT_006, "HIS 患者 ID 已存在")
    inpatient_no = request.encounter.inpatient_no.strip()
    if db.scalar(
        select(PatientEncounter.id).where(
            PatientEncounter.inpatient_no == inpatient_no,
            PatientEncounter.deleted == 0,
        )
    ):
        raise AppError(ErrorCode.ERR_PATIENT_006, "住院号已存在")


def create_patient_record(
    db: Session,
    request: PatientCreateRequest,
    *,
    operator: str,
) -> PatientRecordDto:
    """同一事务新增患者主档与当前住院记录。"""
    _ensure_create_unique(db, request)
    secret = get_app_config().security.patient_identity_secret
    patient = Patient(
        patient_no=_new_business_no(db, Patient),
        his_patient_id=_trim(request.patient.his_patient_id),
        patient_name=request.patient.patient_name.strip(),
        sex=request.patient.sex.strip(),
        birthday=request.patient.birthday,
        phone=normalize_phone(request.patient.phone),
        id_card_ciphertext=encrypt_id_card(request.patient.id_card_no, secret),
        emergency_contact_name=_trim(request.patient.emergency_contact_name),
        emergency_contact_relation=_trim(
            request.patient.emergency_contact_relation
        ),
        emergency_contact_phone=(
            normalize_phone(request.patient.emergency_contact_phone)
            if _trim(request.patient.emergency_contact_phone)
            else None
        ),
        address=_trim(request.patient.address),
        creator=operator,
        updator=operator,
    )
    db.add(patient)
    db.flush()
    encounter = PatientEncounter(
        encounter_no=_new_business_no(db, PatientEncounter),
        patient_id=patient.id,
        inpatient_no=request.encounter.inpatient_no.strip(),
        department_code=_trim(request.encounter.department_code),
        department_name=request.encounter.department_name.strip(),
        ward_name=request.encounter.ward_name.strip(),
        bed_no=request.encounter.bed_no.strip(),
        admission_time=request.encounter.admission_time,
        discharge_time=request.encounter.discharge_time,
        diagnosis_snapshot=request.encounter.diagnosis_snapshot,
        encounter_status=request.encounter.encounter_status,
        admission_source=_trim(request.encounter.admission_source),
        nursing_level=_trim(request.encounter.nursing_level),
        insurance_type=_trim(request.encounter.insurance_type),
        allergy_summary=_trim(request.encounter.allergy_summary),
        creator=operator,
        updator=operator,
    )
    db.add(encounter)
    db.commit()
    db.refresh(patient)
    db.refresh(encounter)
    return _record_dto(db, patient, encounter)


def update_patient_record(
    db: Session,
    patient_id: int,
    request: PatientUpdateRequest,
    *,
    operator: str,
) -> PatientRecordDto:
    """更新患者主档与指定当前住院记录，不回写历史评估快照。"""
    patient = db.scalar(
        select(Patient).where(Patient.id == patient_id, Patient.deleted == 0)
    )
    encounter = db.scalar(
        select(PatientEncounter).where(
            PatientEncounter.id == request.encounter.id,
            PatientEncounter.patient_id == patient_id,
            PatientEncounter.deleted == 0,
        )
    )
    if patient is None or encounter is None:
        raise AppError(ErrorCode.ERR_PATIENT_005)

    patient_values = request.patient.model_dump(exclude={"id_card_no"})
    for field_name in request.patient.model_fields_set - {"id_card_no"}:
        value = patient_values[field_name]
        if field_name == "phone" and value is not None:
            value = normalize_phone(value)
        elif field_name == "emergency_contact_phone" and value is not None:
            value = normalize_phone(value)
        elif isinstance(value, str):
            value = _trim(value)
        if field_name == "his_patient_id" and value:
            duplicate_id = db.scalar(
                select(Patient.id).where(
                    Patient.his_patient_id == value,
                    Patient.id != patient.id,
                    Patient.deleted == 0,
                )
            )
            if duplicate_id is not None:
                raise AppError(ErrorCode.ERR_PATIENT_006, "HIS 患者 ID 已存在")
        setattr(patient, field_name, value)
    if request.patient.id_card_no:
        if _id_card_owner(
            db,
            request.patient.id_card_no,
            exclude_patient_id=patient.id,
        ):
            raise AppError(ErrorCode.ERR_PATIENT_006, "该身份证号已存在患者主档")
        patient.id_card_ciphertext = encrypt_id_card(
            normalize_id_card(request.patient.id_card_no),
            get_app_config().security.patient_identity_secret,
        )

    encounter_values = request.encounter.model_dump(exclude={"id"})
    for field_name in request.encounter.model_fields_set - {"id"}:
        value = encounter_values[field_name]
        if isinstance(value, str):
            value = _trim(value)
        setattr(encounter, field_name, value)
    if "inpatient_no" in request.encounter.model_fields_set:
        duplicate_id = db.scalar(
            select(PatientEncounter.id).where(
                PatientEncounter.inpatient_no == encounter.inpatient_no,
                PatientEncounter.id != encounter.id,
                PatientEncounter.deleted == 0,
            )
        )
        if duplicate_id is not None:
            raise AppError(ErrorCode.ERR_PATIENT_006, "住院号已存在")

    patient.updator = operator
    encounter.updator = operator
    db.commit()
    db.refresh(patient)
    db.refresh(encounter)
    return _record_dto(db, patient, encounter)


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
