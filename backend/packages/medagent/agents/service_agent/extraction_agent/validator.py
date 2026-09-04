"""JSON Schema 校验器
作用：定义 Pydantic 模型，校验 LLM 返回的字段抽取结果
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .types import AnswerType


class ExtractionCandidate(BaseModel):
    """模型直接返回的最终答案候选。"""

    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(..., description="AI 判断能够填写的题目ID")
    answer_type: AnswerType = Field(..., description="AI 已规范化的答案类型")
    answer_value: str | float | bool | None = Field(
        None,
        description="文本、数值、布尔或日期答案；选择题保持为空",
    )
    selected_option_codes: list[str] = Field(
        default_factory=list,
        description="选择题直接返回题目定义中的 option_code",
    )
    evidence: str = Field(..., min_length=1, description="患者原话依据")
    confidence: float = Field(..., ge=0.0, le=1.0, description="候选置信度")


class ExtractedAnswer(BaseModel):
    """单个字段的抽取结果"""

    question_id: int = Field(..., description="问题ID")
    question_code: str = Field(..., description="问题编码")
    answer_type: AnswerType = Field(..., description="答案类型")

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


class InvalidExtractedAnswer(BaseModel):
    """单个候选校验失败的诊断记录。"""

    model_config = ConfigDict(extra="allow")

    question_id: int | None = None
    question_code: str | None = None
    answer_type: str | None = None
    raw_answer: dict[str, Any] = Field(default_factory=dict)
    error: str


class RawExtractionResult(BaseModel):
    """提供给模型的最小结构化响应。"""

    model_config = ConfigDict(extra="forbid")

    answers: list[ExtractionCandidate] = Field(..., description="本轮能够填写的答案候选")


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
    invalid_answers: list[InvalidExtractedAnswer] = Field(
        default_factory=list,
        description="仅记录单字段校验失败，不影响同批有效字段写入",
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
