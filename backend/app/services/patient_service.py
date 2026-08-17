"""患者服务
作用：封装患者与住院记录的查询逻辑。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient_task import Patient, PatientEncounter
from app.schemas.patient import InHospitalPatientDto, PatientDto, PatientEncounterDto

logger = logging.getLogger(__name__)


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
