"""JSON Schema 校验器
作用：定义 Pydantic 模型，校验 LLM 返回的字段抽取结果
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExtractedAnswer(BaseModel):
    """单个字段的抽取结果"""

    question_id: int = Field(..., description="问题ID")
    question_code: str = Field(..., description="问题编码")
    answer_type: Literal[
        "text", "number", "boolean", "date", "single_choice", "multiple_choice"
    ] = Field(..., description="答案类型")

    # 基础答案字段（根据 answer_type 填充对应字段）
    answer_value: str | float | bool | date | None = Field(
        None, description="答案值（文本/数字/布尔/日期）"
    )

    # 选择题专用字段
    selected_option_codes: list[str] = Field(
        default_factory=list, description="选中的选项编码列表"
    )

    # 附加输入（如"其他"补充、数量、单位）
    extra_inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="附加输入，如 {'years': 20, 'frequency': 15, 'unit': '支/天'}",
    )

    # 临床得分
    clinical_score: float | None = Field(None, description="该题临床得分")

    # 置信度与来源
    extraction_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="抽取置信度（0.0-1.0）"
    )
    source_message_ids: list[str] = Field(
        default_factory=list, description="来源消息ID列表"
    )

    # 推理过程
    reasoning: str = Field(..., description="抽取推理过程（便于调试）")

    @field_validator("extraction_confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """校验置信度范围"""
        if not 0.0 <= v <= 1.0:
            raise ValueError("extraction_confidence 必须在 0.0-1.0 之间")
        return v


class ExtractionResult(BaseModel):
    """完整的字段抽取结果"""

    extracted_answers: list[ExtractedAnswer] = Field(
        ..., description="抽取的字段列表"
    )
    overall_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="整体抽取置信度"
    )
    missing_questions: list[int] = Field(
        default_factory=list, description="尚未问到的题目ID列表"
    )
    ambiguous_questions: list[int] = Field(
        default_factory=list, description="回答不清晰的题目ID列表"
    )

    @field_validator("overall_confidence")
    @classmethod
    def validate_overall_confidence(cls, v: float) -> float:
        """校验整体置信度范围"""
        if not 0.0 <= v <= 1.0:
            raise ValueError("overall_confidence 必须在 0.0-1.0 之间")
        return v


def validate_extraction_result(raw_json: dict) -> ExtractionResult:
    """校验并解析 LLM 返回的 JSON
    作用：使用 Pydantic 自动校验 + 返回类型化对象
    Args:
        - raw_json: LLM 返回的原始 JSON 字典
    Return:
        - 校验通过的 ExtractionResult 对象
    Raises:
        - ValidationError: JSON 格式不符合 Schema
    """
    return ExtractionResult.model_validate(raw_json)
