"""护士 AI 质量评价接口 Schema。
作用：约束逐条消息质评和整次会话质量评价的请求、查询与响应。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Score = Annotated[int, Field(ge=1, le=5)]


class MessageRatingRequest(BaseModel):
    """护士对单条 AI 消息进行逐轮质评。"""

    model_config = ConfigDict(extra="forbid")

    task_id: int | str = Field(..., description="任务主键或任务编号")
    message_id: int | str = Field(..., description="消息主键或消息编号")
    reviewer_id: int = Field(default=0, ge=0, description="护士工号对应的数值ID")
    rating: Literal["like", "dislike"] | None = Field(
        default=None,
        description="兼容原有点赞/点踩标注",
    )
    score: Score | None = Field(default=None, description="1～5分逐条质评")
    issue_tags: list[str] = Field(default_factory=list, max_length=20)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_rating_or_score(self) -> "MessageRatingRequest":
        """至少提交点赞/点踩或 1～5 分中的一种。"""
        if self.rating is None and self.score is None:
            raise ValueError("rating 与 score 至少填写一项")
        return self


class MessageRatingResponse(BaseModel):
    """逐条消息质评结果。"""

    feedback_id: int
    task_id: str
    message_id: str
    reviewer_id: int
    rating: Literal["like", "dislike"]
    score: int | None = None
    issue_tags: list[str] = Field(default_factory=list)
    comment: str | None = None
    reviewed_at: datetime


class MessageRatingListResponse(BaseModel):
    """某任务下护士逐条质评列表。"""

    items: list[MessageRatingResponse] = Field(default_factory=list)


class QualityReviewRequest(BaseModel):
    """护士对一次 AI 对话和 AI 评估结果进行整体评价。"""

    model_config = ConfigDict(extra="forbid")

    task_id: int | str = Field(..., description="任务主键或任务编号")
    reviewer_id: int = Field(default=0, ge=0, description="护士工号对应的数值ID")
    dialogue_scores: dict[str, Score] = Field(default_factory=dict)
    assessment_scores: dict[str, Score] = Field(default_factory=dict)
    dialogue_comments: dict[str, str] = Field(default_factory=dict)
    assessment_comments: dict[str, str] = Field(default_factory=dict)
    evidence_message_ids: dict[str, list[str]] = Field(default_factory=dict)
    evidence_question_ids: dict[str, list[str]] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=5000)

    @field_validator(
        "dialogue_comments",
        "assessment_comments",
        mode="before",
    )
    @classmethod
    def normalize_comments(cls, value: object) -> dict[str, str]:
        """将空值归一化为字典，避免前端未填写时接口失败。"""
        return value if isinstance(value, dict) else {}

    @model_validator(mode="after")
    def validate_at_least_one_dimension(self) -> "QualityReviewRequest":
        """整体评价至少应保存一组评分维度。"""
        if not self.dialogue_scores and not self.assessment_scores:
            raise ValueError("dialogue_scores 与 assessment_scores 至少填写一组")
        return self


class QualityReviewResponse(BaseModel):
    """一次任务的整体质量评价汇总。"""

    task_id: str
    reviewer_id: int
    dialogue_scores: dict[str, float] = Field(default_factory=dict)
    assessment_scores: dict[str, float] = Field(default_factory=dict)
    dialogue_comments: dict[str, str] = Field(default_factory=dict)
    assessment_comments: dict[str, str] = Field(default_factory=dict)
    comment: str | None = None
    submitted_at: datetime | None = None
