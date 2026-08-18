"""患者相关 Schema
作用：定义在院患者查询响应结构。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.task import BackendTaskDto


class PatientDto(BaseModel):
    """患者基本信息 DTO
    作用：与前端 Patient 类型对齐。
    """

    id: int = Field(..., description="患者主键（返回前端时转字符串）")
    patient_no: str = Field(..., description="患者编号")
    patient_name: str = Field(..., description="患者姓名")
    sex: str | None = Field(default=None, description="性别")
    birthday: date | None = Field(default=None, description="出生日期")
    phone: str | None = Field(default=None, description="联系电话")


class PatientEncounterDto(BaseModel):
    """住院记录 DTO
    作用：与前端 PatientEncounter 类型对齐。
    """

    id: int = Field(..., description="住院记录主键")
    encounter_no: str = Field(..., description="就诊编号")
    inpatient_no: str | None = Field(default=None, description="住院号")
    patient_id: int = Field(..., description="患者ID")
    department_code: str | None = Field(default=None, description="科室代码")
    department_name: str | None = Field(default=None, description="科室名称")
    ward_name: str | None = Field(default=None, description="病区名称")
    bed_no: str | None = Field(default=None, description="床号")
    admission_time: datetime = Field(..., description="入院时间")
    encounter_status: str = Field(..., description="就诊状态")
    diagnosis_snapshot: dict | None = Field(default=None, description="诊断快照")


class InHospitalPatientDto(BaseModel):
    """在院患者响应项
    作用：包含患者与当前住院记录，供前端患者列表使用。
    """

    patient: PatientDto
    encounter: PatientEncounterDto


class PatientLoginRequest(BaseModel):
    """患者登录请求
    作用：使用身份证号和手机号核验患者身份。
    """

    id_card_no: str = Field(..., min_length=6, max_length=32, description="身份证号")
    phone: str = Field(..., min_length=6, max_length=32, description="手机号")


class PatientLoginResponse(BaseModel):
    """患者登录响应
    作用：返回已核验患者的当前住院记录和本人护理任务。
    """

    patient: PatientDto
    encounter: PatientEncounterDto
    tasks: list[BackendTaskDto] = Field(default_factory=list)
