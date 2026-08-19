"""字段抽取相关 Schema
作用：定义抽取字段查询响应结构。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedFieldDto(BaseModel):
    """抽取字段 DTO
    作用：与前端 ExtractedFieldDto 类型对齐。
    """

    field_id: str | None = Field(default=None, description="字段唯一ID（可选）")
    question_id: int = Field(..., description="问题ID")
    question_code: str = Field(..., description="问题编码")
    question_text: str = Field(..., description="问题文本")
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


class ExtractedFieldsResponse(BaseModel):
    """抽取字段查询响应
    作用：返回指定会话的所有抽取字段。
    """

    session_id: str = Field(..., description="会话编号")
    fields: list[ExtractedFieldDto] = Field(
        default_factory=list, description="抽取字段列表"
    )
