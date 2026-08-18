"""AI 质量评价域 ORM 模型。
作用：保存护士对单次 AI 对话、AI 评估结果以及逐项维度的可追溯评价。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class QualityReviewTemplate(BusinessBaseMixin, Base):
    """AI 对话或 AI 评估使用的质量评价模板。"""

    __tablename__ = "quality_review_template"

    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score_scale: Mapped[str] = mapped_column(String(32), nullable=False, default="1-5")
    version_code: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enabled")

    __table_args__ = (
        UniqueConstraint(
            "template_code",
            "version_code",
            name="uq_quality_review_template_code",
        ),
        Index("idx_quality_review_template_target", "target_type", "status", "deleted"),
    )


class QualityReviewDimension(BusinessBaseMixin, Base):
    """质量评价模板中的可配置评分维度。"""

    __tablename__ = "quality_review_dimension"

    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("quality_review_template.id", ondelete="CASCADE"),
        nullable=False,
    )
    dimension_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension_description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=1)
    max_score: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=5)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "dimension_code",
            name="uq_quality_review_dimension_code",
        ),
        Index("idx_quality_review_dimension_template", "template_id", "deleted"),
    )


class QualityReview(BusinessBaseMixin, Base):
    """护士对某次 AI 对话或 AI 评估的总体评价。"""

    __tablename__ = "quality_review"

    review_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("quality_review_template.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # target_id 按 target_type 指向 interaction_session 或 assessment_submission，
    # 不声明物理外键，避免多态目标被错误约束。
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    patient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient_encounter.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    issue_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_quality_review_target_reviewer",
            "target_type",
            "target_id",
            "reviewer_id",
            "deleted",
        ),
        Index("idx_quality_review_patient", "patient_id", "encounter_id", "deleted"),
    )


class QualityReviewScore(BusinessBaseMixin, Base):
    """质量评价的分项得分、意见和证据消息。"""

    __tablename__ = "quality_review_score"

    quality_review_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("quality_review.id", ondelete="CASCADE"),
        nullable=False,
    )
    dimension_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("quality_review_dimension.id", ondelete="RESTRICT"),
        nullable=False,
    )
    score_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    score_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_message_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_question_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint(
            "quality_review_id",
            "dimension_id",
            name="uq_quality_review_score_dimension",
        ),
        Index("idx_quality_review_score_review", "quality_review_id", "deleted"),
    )
