"""患者画像与护理计划 Schema
作用：定义 AI 结构化输出、医护端查询、编辑和确认请求。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["low", "medium", "high", "unknown"]
PlanPriority = Literal["low", "medium", "high"]
PlanItemType = Literal[
    "nursing_measure",
    "education",
    "observation",
    "handover",
]
NurseAction = Literal["pending", "accepted", "modified", "rejected"]


class AiPatientProfile(BaseModel):
    """模型生成的患者画像字段。"""

    cooperation_level: Literal["good", "partial", "poor", "unknown"]
    cognition_level: Literal[
        "clear",
        "mild_impairment",
        "impaired",
        "unknown",
    ]
    self_care_level: Literal[
        "independent",
        "partial_assistance",
        "dependent",
        "unknown",
    ]
    fall_risk_level: RiskLevel
    pressure_risk_level: RiskLevel
    nutrition_risk_level: RiskLevel
    communication_level: Literal["good", "limited", "difficult", "unknown"]
    education_need_level: Literal["low", "medium", "high"]
    summary: str = Field(..., min_length=1, max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=30)


class AiNursingPlanItem(BaseModel):
    """模型生成的一条护理指导建议。"""

    item_type: PlanItemType
    item_code: str = Field(..., min_length=1, max_length=64)
    item_content: str = Field(..., min_length=1, max_length=2000)
    source_type: Literal[
        "assessment_answer",
        "assessment_score",
        "risk_event",
        "dialogue_summary",
    ]
    source_id: str | None = Field(default=None, max_length=64)
    priority: PlanPriority


class AiNursingPlanOutput(BaseModel):
    """真实模型必须返回的患者画像与护理计划结构。"""

    profile: AiPatientProfile
    risk_summary: str = Field(..., min_length=1, max_length=4000)
    education_summary: str = Field(..., min_length=1, max_length=4000)
    handover_summary: str = Field(..., min_length=1, max_length=4000)
    items: list[AiNursingPlanItem] = Field(..., min_length=1, max_length=30)


class PatientProfileDto(BaseModel):
    """患者画像快照响应。"""

    id: int
    profile_no: str
    source_submission_ids: list[int]
    cooperation_level: str
    cognition_level: str
    self_care_level: str
    fall_risk_level: str
    pressure_risk_level: str
    nutrition_risk_level: str
    communication_level: str
    education_need_level: str
    profile_detail: dict[str, Any]
    generated_by: str
    generated_at: str


class NursingPlanItemDto(BaseModel):
    """护理计划明细响应。"""

    id: int
    item_type: str
    item_code: str
    item_content: str
    source_type: str
    source_id: str | None = None
    priority: str
    nurse_action: str
    nurse_comment: str | None = None


class NursingPlanDto(BaseModel):
    """护理计划及患者画像组合响应。"""

    id: int
    task_id: int
    plan_no: str
    plan_status: str
    risk_summary: str
    education_summary: str
    handover_summary: str
    generated_by: str
    confirmed_by: int | None = None
    confirmed_at: str | None = None
    profile: PatientProfileDto
    items: list[NursingPlanItemDto]


class NursingPlanGenerateRequest(BaseModel):
    """生成或重新生成护理计划请求。"""

    model_config = ConfigDict(extra="forbid")
    force: bool = False


class NursingPlanItemUpdate(BaseModel):
    """护士编辑一条已有护理计划明细。"""

    model_config = ConfigDict(extra="forbid")

    id: int
    item_content: str = Field(..., min_length=1, max_length=2000)
    priority: PlanPriority
    nurse_action: NurseAction
    nurse_comment: str | None = Field(default=None, max_length=2000)


class NursingPlanUpdateRequest(BaseModel):
    """护士直接编辑护理计划草案请求。"""

    model_config = ConfigDict(extra="forbid")

    risk_summary: str = Field(..., min_length=1, max_length=4000)
    education_summary: str = Field(..., min_length=1, max_length=4000)
    handover_summary: str = Field(..., min_length=1, max_length=4000)
    items: list[NursingPlanItemUpdate] = Field(..., min_length=1)
