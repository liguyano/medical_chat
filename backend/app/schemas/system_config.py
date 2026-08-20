"""Demo 系统配置 Schema
作用：定义宣教材料、拦截特征字典和评估量表的查看与直接更新结构。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EducationMaterialConfigDto(BaseModel):
    """宣教材料扁平配置。"""

    id: int
    version_id: int
    unit_id: int
    category: str
    title: str
    document_version: str
    original_content: str
    patient_content: str
    spoken_content: str
    source_name: str | None = None
    priority: str
    requires_acknowledgement: bool
    auto_play: bool
    enabled: bool


class EducationMaterialUpdateRequest(BaseModel):
    """宣教材料直接更新请求。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=128)
    document_version: str = Field(..., min_length=1, max_length=64)
    original_content: str = Field(..., min_length=1)
    patient_content: str = Field(..., min_length=1)
    spoken_content: str = Field(..., min_length=1)
    source_name: str | None = Field(default=None, max_length=256)
    priority: str = Field(..., pattern="^(low|medium|high)$")
    requires_acknowledgement: bool = True
    auto_play: bool = True
    enabled: bool = True


class InteractionRuleConfigDto(BaseModel):
    """拦截特征规则配置。"""

    id: int
    rule_code: str
    rule_name: str
    scope_type: str
    scope_id: int | None = None
    keywords: list[str]
    patterns: list[str]
    action_type: str
    prompt: str
    tags: list[str]
    priority: int
    enabled: bool


class InteractionRuleUpdateRequest(BaseModel):
    """拦截特征规则直接更新请求。"""

    model_config = ConfigDict(extra="forbid")

    rule_name: str = Field(..., min_length=1, max_length=128)
    scope_type: str = Field(..., min_length=1, max_length=32)
    scope_id: int | None = None
    keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    action_type: str = Field(..., min_length=1, max_length=32)
    prompt: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    priority: int = Field(default=0, ge=-10000, le=10000)
    enabled: bool = True

    @field_validator("keywords", "patterns", "tags")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        """清理空值并保持输入顺序去重。"""
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result


class InteractionRuleTestRequest(BaseModel):
    """拦截特征测试请求。"""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1, max_length=2000)


class InteractionRuleMatchDto(BaseModel):
    """测试命中结果。"""

    rule_code: str
    rule_name: str
    matched_terms: list[str]
    action_type: str
    prompt: str
    priority: int


class AssessmentScaleConfigSummaryDto(BaseModel):
    """量表配置摘要。"""

    id: int
    scale_code: str
    scale_name: str
    scale_type: str
    clinical_purpose: str | None = None
    status: str
    version_id: int
    version_code: str
    version_name: str
    publish_status: str
    section_count: int
    question_count: int
    option_count: int
    rule_count: int
    action_count: int


class AssessmentSectionConfigDto(BaseModel):
    """量表分组配置。"""

    id: int
    parent_section_id: int | None = None
    section_code: str
    section_name: str
    section_description: str | None = None
    display_condition: dict[str, Any] | None = None
    sort_no: int


class AssessmentQuestionConfigDto(BaseModel):
    """量表问题配置。"""

    id: int
    section_id: int | None = None
    question_code: str
    question_name: str
    original_text: str
    patient_text: str
    nurse_text: str | None = None
    question_type: str
    value_type: str
    required: bool
    scored: bool
    unit: str | None = None
    value_precision: int | None = None
    allow_other: bool
    derived: bool
    calculation_expression: str | None = None
    validation_rule: dict[str, Any] | None = None
    sort_no: int


class AssessmentOptionConfigDto(BaseModel):
    """量表选项配置。"""

    id: int
    question_id: int
    option_code: str
    option_label: str
    option_value: str
    clinical_score: float | None = None
    risk_tag: str | None = None
    requires_follow_up: bool
    extra_input_type: str | None = None
    extra_input_unit: str | None = None
    sort_no: int


class AssessmentRuleConfigDto(BaseModel):
    """量表计算规则配置。"""

    id: int
    rule_code: str
    rule_type: str
    condition_expression: dict[str, Any]
    result_payload: dict[str, Any]
    priority: int
    status: str


class AssessmentActionConfigDto(BaseModel):
    """量表护理措施配置。"""

    id: int
    action_code: str
    action_group: str | None = None
    action_name: str
    action_type: str
    input_type: str
    allow_other: bool
    trigger_rule_id: int | None = None
    sort_no: int


class AssessmentScaleConfigDetailDto(BaseModel):
    """量表当前版本完整配置。"""

    id: int
    scale_code: str
    scale_name: str
    scale_type: str
    clinical_purpose: str | None = None
    applicable_scope: dict[str, Any] | None = None
    source_file: str | None = None
    status: str
    version_id: int
    version_code: str
    version_name: str
    publish_status: str
    scale_snapshot: dict[str, Any]
    sections: list[AssessmentSectionConfigDto]
    questions: list[AssessmentQuestionConfigDto]
    options: list[AssessmentOptionConfigDto]
    rules: list[AssessmentRuleConfigDto]
    actions: list[AssessmentActionConfigDto]


class AssessmentScaleConfigUpdateRequest(AssessmentScaleConfigDetailDto):
    """量表当前版本直接更新请求。"""

    model_config = ConfigDict(extra="forbid")
