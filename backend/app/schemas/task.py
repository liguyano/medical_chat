"""评估任务相关 Schema
作用：定义任务创建请求与任务详情响应结构。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    """创建评估任务请求
    作用：承载前端创建 care_task 所需字段（对齐前端 CreateTaskRequest 契约）。
    """

    patient_id: int = Field(..., description="患者ID")
    encounter_id: int = Field(..., description="住院记录ID")
    nurse_id: int = Field(..., description="负责护士ID")
    scale_ids: list[int] = Field(..., description="量表ID列表")
    collection_mode: str = Field(..., description="采集模式：questionnaire 或 ai_dialog")
    participant_type: str = Field(..., description="参与者类型：patient/family/caregiver")
    participant_name: str | None = Field(default=None, description="参与者姓名")
    relationship_to_patient: str | None = Field(default=None, description="与患者关系")
    assessment_scene: str = Field(..., description="评估场景：admission/discharge/transfer等")
    consent_required: bool = Field(..., description="是否需要知情同意")
    education_topics: list[str] = Field(default_factory=list, description="宣教主题列表")
    planned_start_time: datetime | None = Field(default=None, description="计划开始时间")
    notes: str | None = Field(default=None, description="备注")
    task_type: str = Field(default="assessment", description="任务类型")
    task_name: str = Field(default="入院量表评估", description="任务名称")
    task_source: str = Field(default="manual", description="任务来源")


class CreateTaskResponse(BaseModel):
    """创建任务响应
    作用：返回新建任务的关键标识（对齐前端 CreateTaskResponse 契约）。
    """

    task_id: int = Field(..., description="任务主键")
    task_no: str = Field(..., description="任务编号")
    session_id: str | None = Field(default=None, description="会话编号（ai_dialog模式预建）")
    status: str = Field(..., description="任务状态")
    task: "BackendTaskDto | None" = Field(default=None, description="完整任务详情（可选）")


class BackendTaskDto(BaseModel):
    """任务详情响应（对齐前端 BackendTaskDto 契约）
    作用：向前端返回任务完整字段，供详情页与监控页使用。
    """

    id: int | None = Field(default=None, description="任务主键（兼容）")
    task_id: int | None = Field(default=None, description="任务主键（兼容）")
    task_no: str = Field(..., description="任务编号")
    session_id: str | None = Field(default=None, description="会话编号")
    patient_id: int = Field(..., description="患者ID")
    encounter_id: int = Field(..., description="住院记录ID")
    encounter_no: str | None = Field(default=None, description="就诊编号")
    patient_name: str | None = Field(default=None, description="患者姓名")
    bed_no: str | None = Field(default=None, description="床号")
    department: str | None = Field(default=None, description="科室")
    ward_name: str | None = Field(default=None, description="病区")
    task_type: str | None = Field(default=None, description="任务类型")
    collection_mode: str = Field(..., description="采集模式")
    task_status: str = Field(..., description="任务状态")
    nurse_id: int | None = Field(default=None, description="护士ID（兼容）")
    assigned_nurse_id: int | None = Field(default=None, description="负责护士ID")
    assigned_nurse_name: str | None = Field(default=None, description="负责护士姓名")
    scale_ids: list[int] | None = Field(default=None, description="量表ID列表")
    scale_names: list[str] | None = Field(default=None, description="量表名称列表")
    scale_version: str | None = Field(default=None, description="量表版本")
    participant_type: str | None = Field(default=None, description="参与者类型")
    participant_name: str | None = Field(default=None, description="参与者姓名")
    relationship_to_patient: str | None = Field(default=None, description="与患者关系")
    assessment_scene: str | None = Field(default=None, description="评估场景")
    consent_required: bool | None = Field(default=None, description="是否需要知情同意")
    education_topics: list[str] | None = Field(default=None, description="宣教主题列表")
    planned_start_time: str | None = Field(default=None, description="计划开始时间")
    notes: str | None = Field(default=None, description="备注")
    handoff_required: bool | None = Field(default=None, description="是否需要人工介入")
    handoff_reason: str | None = Field(default=None, description="介入原因")
    current_stage: str | None = Field(default=None, description="当前阶段")
    ai_summary: str | None = Field(default=None, description="AI总结")
    answered_question_count: int | None = Field(default=None, description="已回答题目数")
    total_question_count: int | None = Field(default=None, description="总题目数")
    created_at: str = Field(..., description="创建时间")
    updated_at: str | None = Field(default=None, description="更新时间")
    completed_at: str | None = Field(default=None, description="完成时间")
