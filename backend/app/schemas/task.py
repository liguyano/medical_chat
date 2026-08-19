"""评估任务相关 Schema
作用：定义第一期文本评估任务的创建请求与详情响应结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateTaskRequest(BaseModel):
    """创建评估任务请求
    作用：承载任务、参与者和量表选择；字段分别落入任务、会话与评估实例。
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(..., description="患者ID")
    encounter_id: int = Field(..., description="住院记录ID")
    scale_ids: list[int] = Field(..., min_length=1, description="量表ID列表")
    collection_mode: Literal["traditional_form", "ai_dialogue"] = Field(
        default="ai_dialogue",
        description="采集模式",
    )
    participant_type: Literal["patient", "family", "agent"] = Field(
        default="patient",
        description="参与者类型",
    )
    assessment_scene: Literal["admission", "reassessment", "transfer", "discharge"] = Field(
        default="admission", description="评估场景"
    )
    assigned_nurse_id: int | None = Field(default=None, description="负责护士ID")
    planned_start_time: datetime | None = Field(default=None, description="计划开始时间")
    task_type: str = Field(default="assessment", description="任务类型")
    task_name: str = Field(default="入院量表评估", description="任务名称")
    task_source: str = Field(default="manual", description="任务来源")


class TaskScaleProgressDto(BaseModel):
    """任务目标量表进度。"""

    scale_id: int
    scale_name: str
    answered_question_count: int = 0
    total_question_count: int = 0
    status: Literal["pending", "collecting", "completed"]


class BackendTaskDto(BaseModel):
    """任务详情响应
    作用：返回页面展示和实时会话所需的完整任务信息。
    """

    id: int
    task_id: int
    task_no: str
    session_id: str | None = None
    patient_id: int
    encounter_id: int
    encounter_no: str
    patient_name: str
    inpatient_no: str | None = None
    bed_no: str | None = None
    department: str | None = None
    ward_name: str | None = None
    sex: str | None = None
    age: int | None = None
    admission_time: str | None = None
    encounter_status: str | None = None
    task_type: str
    collection_mode: Literal["traditional_form", "ai_dialogue"]
    task_status: str
    assigned_nurse_id: int | None = None
    assigned_nurse_name: str | None = None
    scale_ids: list[int] = Field(default_factory=list)
    scale_names: list[str] = Field(default_factory=list)
    scale_progress: list[TaskScaleProgressDto] = Field(default_factory=list)
    scale_version: str | None = None
    participant_type: str | None = None
    assessment_scene: str | None = None
    handoff_required: bool = False
    handoff_reason: str | None = None
    current_stage: str | None = None
    ai_summary: str | None = None
    answered_question_count: int = 0
    total_question_count: int = 0
    planned_start_time: str | None = None
    created_at: str
    updated_at: str | None = None
    completed_at: str | None = None


class CreateTaskResponse(BaseModel):
    """创建任务响应
    作用：返回任务主键、业务编号、会话编号和完整任务详情。
    """

    task_id: int
    task_no: str
    session_id: str | None = None
    status: str
    task: BackendTaskDto
