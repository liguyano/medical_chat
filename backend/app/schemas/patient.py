"""患者相关 Schema
作用：定义医护端患者管理、患者登录和住院记录响应结构。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.task import BackendTaskDto

EncounterStatus = Literal["待入院", "在院", "已出院", "取消"]


class PatientDto(BaseModel):
    """患者基本信息 DTO。"""

    id: int
    patient_no: str
    his_patient_id: str | None = None
    patient_name: str
    sex: str | None = None
    birthday: date | None = None
    phone: str | None = None
    id_card_masked: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relation: str | None = None
    emergency_contact_phone: str | None = None
    address: str | None = None


class PatientEncounterDto(BaseModel):
    """住院记录 DTO。"""

    id: int
    encounter_no: str
    inpatient_no: str | None = None
    patient_id: int
    department_code: str | None = None
    department_name: str | None = None
    ward_name: str | None = None
    bed_no: str | None = None
    admission_time: datetime
    discharge_time: datetime | None = None
    encounter_status: str
    diagnosis_snapshot: dict | None = None
    admission_source: str | None = None
    nursing_level: str | None = None
    insurance_type: str | None = None
    allergy_summary: str | None = None


class PatientTaskSummaryDto(BaseModel):
    """患者当前住院护理任务摘要。"""

    total: int = 0
    pending_review: int = 0
    in_progress: int = 0
    handoff_required: bool = False


class PatientRecordDto(BaseModel):
    """患者主档与当前住院记录组合响应。"""

    patient: PatientDto
    encounter: PatientEncounterDto
    task_summary: PatientTaskSummaryDto = Field(
        default_factory=PatientTaskSummaryDto
    )


class InHospitalPatientDto(PatientRecordDto):
    """兼容原在院患者列表契约。"""


class PatientCreatePayload(BaseModel):
    """新增患者主档输入。"""

    his_patient_id: str | None = Field(default=None, max_length=64)
    patient_name: str = Field(..., min_length=1, max_length=128)
    sex: str = Field(..., min_length=1, max_length=16)
    birthday: date
    id_card_no: str = Field(..., min_length=6, max_length=32)
    phone: str = Field(..., min_length=6, max_length=32)
    emergency_contact_name: str | None = Field(default=None, max_length=128)
    emergency_contact_relation: str | None = Field(default=None, max_length=32)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=512)


class PatientEncounterCreatePayload(BaseModel):
    """新增住院记录输入。"""

    inpatient_no: str = Field(..., min_length=1, max_length=64)
    department_code: str | None = Field(default=None, max_length=64)
    department_name: str = Field(..., min_length=1, max_length=128)
    ward_name: str = Field(..., min_length=1, max_length=128)
    bed_no: str = Field(..., min_length=1, max_length=32)
    admission_time: datetime
    discharge_time: datetime | None = None
    encounter_status: EncounterStatus = "在院"
    diagnosis_snapshot: dict | None = None
    admission_source: str | None = Field(default=None, max_length=32)
    nursing_level: str | None = Field(default=None, max_length=32)
    insurance_type: str | None = Field(default=None, max_length=64)
    allergy_summary: str | None = Field(default=None, max_length=2000)


class PatientCreateRequest(BaseModel):
    """患者与本次住院记录一体化新增请求。"""

    patient: PatientCreatePayload
    encounter: PatientEncounterCreatePayload


class PatientUpdatePayload(BaseModel):
    """患者主档更新输入；身份证留空表示保持原值。"""

    his_patient_id: str | None = Field(default=None, max_length=64)
    patient_name: str | None = Field(default=None, min_length=1, max_length=128)
    sex: str | None = Field(default=None, min_length=1, max_length=16)
    birthday: date | None = None
    id_card_no: str | None = Field(default=None, min_length=6, max_length=32)
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    emergency_contact_name: str | None = Field(default=None, max_length=128)
    emergency_contact_relation: str | None = Field(default=None, max_length=32)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=512)


class PatientEncounterUpdatePayload(BaseModel):
    """住院记录更新输入。"""

    id: int = Field(..., gt=0)
    inpatient_no: str | None = Field(default=None, min_length=1, max_length=64)
    department_code: str | None = Field(default=None, max_length=64)
    department_name: str | None = Field(default=None, min_length=1, max_length=128)
    ward_name: str | None = Field(default=None, min_length=1, max_length=128)
    bed_no: str | None = Field(default=None, min_length=1, max_length=32)
    admission_time: datetime | None = None
    discharge_time: datetime | None = None
    encounter_status: EncounterStatus | None = None
    diagnosis_snapshot: dict | None = None
    admission_source: str | None = Field(default=None, max_length=32)
    nursing_level: str | None = Field(default=None, max_length=32)
    insurance_type: str | None = Field(default=None, max_length=64)
    allergy_summary: str | None = Field(default=None, max_length=2000)


class PatientUpdateRequest(BaseModel):
    """患者与当前住院记录一体化更新请求。"""

    patient: PatientUpdatePayload
    encounter: PatientEncounterUpdatePayload


class PatientLoginRequest(BaseModel):
    """患者登录请求。"""

    id_card_no: str = Field(..., min_length=6, max_length=32)
    phone: str = Field(..., min_length=6, max_length=32)


class PatientLoginResponse(BaseModel):
    """患者登录响应。"""

    patient: PatientDto
    encounter: PatientEncounterDto
    tasks: list[BackendTaskDto] = Field(default_factory=list)
