"""评估任务相关 Schema
作用：定义任务创建请求与任务详情响应结构。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    """创建评估任务请求
    作用：承载前端创建 care_task 所需的最小字段。
    """

    patient_id: int = Field(..., description="患者ID")
    encounter_id: int = Field(..., description="住院记录ID")
    task_type: str = Field(default="assessment", description="任务类型")
    task_name: str = Field(default="入院量表评估", description="任务名称")
    task_source: str = Field(default="manual", description="任务来源")
    collection_mode: str = Field(
        default="ai_dialogue",
        description="采集模式：traditional_form 或 ai_dialogue",
    )
    assigned_nurse_id: int | None = Field(default=None, description="负责护士ID")
    planned_start_time: datetime | None = Field(default=None, description="计划开始时间")


class TaskResponse(BaseModel):
    """评估任务详情响应
    作用：向前端返回任务核心字段，供轮询状态。
    """

    task_no: str = Field(..., description="任务编号")
    patient_id: int = Field(..., description="患者ID")
    encounter_id: int = Field(..., description="住院记录ID")
    task_type: str = Field(..., description="任务类型")
    task_name: str = Field(..., description="任务名称")
    task_source: str = Field(..., description="任务来源")
    collection_mode: str | None = Field(default=None, description="采集模式")
    task_status: str = Field(..., description="任务状态")
    assigned_nurse_id: int | None = Field(default=None, description="负责护士ID")
    created_at: datetime | None = Field(default=None, description="创建时间")
