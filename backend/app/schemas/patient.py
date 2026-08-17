"""患者相关 Schema
作用：定义在院患者查询响应结构。
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PatientDto(BaseModel):
    """患者基本信息 DTO
    作用：与前端 Patient 类型对齐。
    """

    id: int = Field(..., description="患者主键（返回前端时转字符串）")
    patient_no: str = Field(..., description="患者编号")
    patient_name: str = Field(..., description="患者姓名")
    sex: str = Field(..., description="性别")
    birthday: date = Field(..., description="出生日期")
    phone: str | None = Field(default=None, description="联系电话")


class PatientEncounterDto(BaseModel):
    """住院记录 DTO
    作用：与前端 PatientEncounter 类型对齐。
    """

    id: int = Field(..., description="住院记录主键")
    encounter_no: str = Field(..., description="就诊编号")
    inpatient_no: str = Field(..., description="住院号")
    patient_id: int = Field(..., description="患者ID")
    department_code: str = Field(..., description="科室代码")
    department_name: str = Field(..., description="科室名称")
    ward_name: str = Field(..., description="病区名称")
    bed_no: str = Field(..., description="床号")
    admission_time: datetime = Field(..., description="入院时间")
    encounter_status: str = Field(..., description="就诊状态")
    diagnosis_snapshot: dict | None = Field(default=None, description="诊断快照")


class InHospitalPatientDto(BaseModel):
    """在院患者响应项
    作用：包含患者与当前住院记录，供前端患者列表使用。
    """

    patient: PatientDto
    encounter: PatientEncounterDto
