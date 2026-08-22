"""传统问卷评估 Schema。
作用：定义患者端问卷读取、草稿保存、正式提交和医护端结果回放契约。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QuestionnaireOptionDto(BaseModel):
    """问卷选项展示与提交契约。"""

    id: int
    option_code: str
    option_label: str
    option_value: str
    clinical_score: float | None = None
    requires_follow_up: bool = False
    extra_input_type: str | None = None
    extra_input_unit: str | None = None


class QuestionnaireQuestionDto(BaseModel):
    """一次任务中实际可填写的量表题目快照。"""

    id: int
    scale_id: int
    scale_name: str
    scale_version_id: int
    section_id: int | None = None
    section_name: str | None = None
    question_code: str
    question_text: str
    question_type: str
    value_type: str
    required: bool
    scored: bool
    derived: bool
    unit: str | None = None
    value_precision: int | None = None
    allow_other: bool = False
    validation_rule: dict[str, Any] | None = None
    sort_no: int = 0
    options: list[QuestionnaireOptionDto] = Field(default_factory=list)


class QuestionnaireAnswerDto(BaseModel):
    """面向患者和医护端的结构化答案，包含可读选项值。"""

    question_id: int
    question_code: str
    answer_type: str
    answer_text: str | None = None
    answer_number: float | None = None
    answer_boolean: bool | None = None
    answer_date: str | None = None
    selected_options: list[str] = Field(default_factory=list)
    selected_option_labels: list[str] = Field(default_factory=list)
    selected_option_values: list[str] = Field(default_factory=list)
    display_value: str | None = None
    clinical_score: float | None = None


class QuestionnaireScoreDto(BaseModel):
    """单张量表的规则计分和解释结果。"""

    scale_id: int
    scale_name: str
    total_score: float | None = None
    risk_level: str | None = None
    result_summary: str | None = None


class QuestionnaireDto(BaseModel):
    """传统问卷任务完整快照。"""

    task_id: int
    task_no: str
    collection_mode: Literal["traditional_form"]
    status: Literal[
        "not_started",
        "in_progress",
        "submitted",
        "returned",
        "confirmed",
    ]
    questions: list[QuestionnaireQuestionDto] = Field(default_factory=list)
    answers: list[QuestionnaireAnswerDto] = Field(default_factory=list)
    scores: list[QuestionnaireScoreDto] = Field(default_factory=list)
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


class QuestionnaireAnswersRequest(BaseModel):
    """患者端问卷答案写入请求。

    `answers` 的键支持题目编码或题目数字 ID，值根据题目类型传入
    文本、数字、布尔值、日期字符串、单选编码或多选编码数组。
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    answers: dict[str, Any] = Field(default_factory=dict)
