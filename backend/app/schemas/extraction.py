"""字段抽取相关 Schema
作用：定义抽取字段查询响应结构。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractedFieldDto(BaseModel):
    """抽取字段 DTO
    作用：与前端 ExtractedFieldDto 类型对齐。
    """

    field_id: str | None = Field(default=None, description="字段唯一ID（可选）")
    question_id: int = Field(..., description="问题ID")
    question_code: str = Field(..., description="问题编码")
    question_text: str = Field(..., description="问题文本")
    answer_type: str = Field(default="text", description="统一答案类型")
    options: list[dict] = Field(default_factory=list, description="可选答案项")
    answer_text: str | None = Field(default=None, description="文本答案")
    answer_number: float | None = Field(default=None, description="数值答案")
    answer_boolean: bool | None = Field(default=None, description="布尔答案")
    selected_options: list[str] | None = Field(
        default=None, description="选中选项编码列表"
    )
    selected_option_labels: list[str] | None = Field(
        default=None, description="选中选项的量表显示值（标签）"
    )
    selected_option_values: list[str] | None = Field(
        default=None, description="选中选项的量表真实值"
    )
    display_value: str | None = Field(
        default=None, description="面向患者和医护展示的真实答案值"
    )
    source_message_ids: list[str] | None = Field(
        default=None, description="来源消息ID列表"
    )
    confidence: float | None = Field(default=None, description="抽取置信度")
    corrected: bool | None = Field(default=None, description="是否被护士修正")
    invalid: bool = Field(default=False, description="模型结果是否校验失败")
    invalid_reason: str | None = Field(default=None, description="校验失败原因")
    raw_answer: dict | None = Field(default=None, description="供人工核对的原始结果")


class ExtractedFieldsResponse(BaseModel):
    """抽取字段查询响应
    作用：返回指定会话的所有抽取字段。
    """

    session_id: str = Field(..., description="会话编号")
    fields: list[ExtractedFieldDto] = Field(
        default_factory=list, description="抽取字段列表"
    )
    task_id: int | None = None
    manual_intervention: bool = False
    intervention_reason: str | None = None


class ManualFieldUpdateRequest(BaseModel):
    """医护人工填写单个结构化字段。"""

    question_id: int
    answer_type: Literal[
        "text", "number", "boolean", "date", "single_choice", "multiple_choice"
    ]
    answer_text: str | None = None
    answer_number: float | None = None
    answer_boolean: bool | None = None
    answer_date: str | None = None
    selected_option_codes: list[str] = Field(default_factory=list)
    extra_inputs: dict[str, Any] = Field(default_factory=dict)
    complete_manual: bool = False
