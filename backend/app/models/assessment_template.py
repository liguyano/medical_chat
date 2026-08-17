"""评估模板域 ORM 模型
作用：定义量表、版本、分组、问题、选项、规则和处置定义。
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class AssessmentScale(BusinessBaseMixin, Base):
    """评估表主档。"""

    __tablename__ = "assessment_scale"

    scale_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scale_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scale_type: Mapped[str] = mapped_column(String(32), nullable=False)
    clinical_purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applicable_scope: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("idx_assessment_scale_status", "status", "deleted"),)


class AssessmentScaleVersion(BusinessBaseMixin, Base):
    """评估表可执行版本。"""

    __tablename__ = "assessment_scale_version"

    scale_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version_name: Mapped[str] = mapped_column(String(128), nullable=False)
    publish_status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scale_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("scale_id", "version_code", name="uq_scale_version_code"),
        Index("idx_scale_version_status", "scale_id", "publish_status", "deleted"),
    )


class AssessmentSection(BusinessBaseMixin, Base):
    """评估表分组。"""

    __tablename__ = "assessment_section"

    scale_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_section_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("assessment_section.id", ondelete="RESTRICT"),
        nullable=True,
    )
    section_code: Mapped[str] = mapped_column(String(64), nullable=False)
    section_name: Mapped[str] = mapped_column(String(128), nullable=False)
    section_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_condition: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("scale_version_id", "section_code", name="uq_section_version_code"),
        Index("idx_section_version_sort", "scale_version_id", "sort_no"),
    )


class AssessmentQuestion(BusinessBaseMixin, Base):
    """评估问题。"""

    __tablename__ = "assessment_question"

    scale_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("assessment_section.id", ondelete="RESTRICT"),
        nullable=True,
    )
    question_code: Mapped[str] = mapped_column(String(64), nullable=False)
    question_name: Mapped[str] = mapped_column(String(256), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    patient_text: Mapped[str] = mapped_column(Text, nullable=False)
    nurse_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    value_precision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allow_other: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calculation_expression: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_rule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("scale_version_id", "question_code", name="uq_question_version_code"),
        Index("idx_question_version_sort", "scale_version_id", "sort_no"),
        Index("idx_question_section", "section_id", "sort_no"),
    )


class AssessmentOption(BusinessBaseMixin, Base):
    """评估选项。"""

    __tablename__ = "assessment_option"

    question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_question.id", ondelete="CASCADE"),
        nullable=False,
    )
    option_code: Mapped[str] = mapped_column(String(64), nullable=False)
    option_label: Mapped[str] = mapped_column(String(256), nullable=False)
    option_value: Mapped[str] = mapped_column(String(256), nullable=False)
    clinical_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    risk_tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requires_follow_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra_input_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    extra_input_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("question_id", "option_code", name="uq_option_question_code"),
        Index("idx_option_question_sort", "question_id", "sort_no"),
    )


class AssessmentRule(BusinessBaseMixin, Base):
    """评估计算与结果规则。"""

    __tablename__ = "assessment_rule"

    scale_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_expression: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("scale_version_id", "rule_code", name="uq_rule_version_code"),
        Index("idx_rule_version_priority", "scale_version_id", "priority"),
    )


class AssessmentActionDefinition(BusinessBaseMixin, Base):
    """评估处置与措施定义。"""

    __tablename__ = "assessment_action_definition"

    scale_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    action_group: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action_name: Mapped[str] = mapped_column(String(256), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    input_type: Mapped[str] = mapped_column(String(32), nullable=False)
    allow_other: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trigger_rule_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("assessment_rule.id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("scale_version_id", "action_code", name="uq_action_version_code"),
        Index("idx_action_version_sort", "scale_version_id", "sort_no"),
    )
