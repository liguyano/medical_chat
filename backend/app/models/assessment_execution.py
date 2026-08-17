"""评估执行域 ORM 模型
作用：定义评估实例、多方提交、结构化答案、选项、临床得分和护士复核。
"""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class AssessmentInstance(BusinessBaseMixin, Base):
    """患者在一次住院中针对某一量表的一次评估容器。"""

    __tablename__ = "assessment_instance"

    instance_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("care_task.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
    scale_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scale_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_scale_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assessment_scene: Mapped[str] = mapped_column(String(32), nullable=False)
    instance_status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assessor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    patient_name_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    sex_snapshot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    age_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    department_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ward_name_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bed_no_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    inpatient_no_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnosis_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    form_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("idx_assessment_instance_task", "task_id", "deleted"),
        Index("idx_assessment_instance_patient", "patient_id", "deleted"),
        Index("idx_assessment_instance_status", "instance_status", "deleted"),
    )


class AssessmentSubmission(BusinessBaseMixin, Base):
    """某一参与方针对评估实例提交的一整套结果。"""

    __tablename__ = "assessment_submission"

    submission_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    assessment_instance_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    submission_type: Mapped[str] = mapped_column(String(32), nullable=False)
    submitter_type: Mapped[str] = mapped_column(String(32), nullable=False)
    submitter_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    interaction_session_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("interaction_session.id", ondelete="SET NULL"),
        nullable=True,
    )
    submission_status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    total_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answered_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_submission_instance_type", "assessment_instance_id", "submission_type", "deleted"),
        Index("idx_submission_session", "interaction_session_id"),
        Index("idx_submission_status", "submission_status", "deleted"),
    )


class AssessmentAnswer(BusinessBaseMixin, Base):
    """某次提交中一道题的结构化答案。"""

    __tablename__ = "assessment_answer"

    submission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_submission.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_question.id", ondelete="RESTRICT"),
        nullable=False,
    )
    answer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    answer_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    answer_time: Mapped[time | None] = mapped_column(Time(timezone=True), nullable=True)
    answer_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    clinical_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    source_message_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    value_source: Mapped[str] = mapped_column(String(32), nullable=False)
    abnormal_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("submission_id", "question_id", name="uq_answer_submission_question"),
        Index("idx_answer_question", "question_id"),
        Index("idx_answer_abnormal", "abnormal_flag", "deleted"),
    )


class AssessmentAnswerOption(BusinessBaseMixin, Base):
    """单选或多选题的选项明细。"""

    __tablename__ = "assessment_answer_option"

    assessment_answer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_answer.id", ondelete="CASCADE"),
        nullable=False,
    )
    option_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_option.id", ondelete="RESTRICT"),
        nullable=False,
    )
    option_code_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    option_label_snapshot: Mapped[str] = mapped_column(String(256), nullable=False)
    clinical_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    extra_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    extra_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    selected_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("assessment_answer_id", "option_id", name="uq_answer_option"),
        Index("idx_answer_option_answer", "assessment_answer_id"),
    )


class AssessmentScore(BusinessBaseMixin, Base):
    """某次评估提交的临床得分、风险等级和解释。"""

    __tablename__ = "assessment_score"

    submission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_submission.id", ondelete="CASCADE"),
        nullable=False,
    )
    score_code: Mapped[str] = mapped_column(String(64), nullable=False)
    score_name: Mapped[str] = mapped_column(String(128), nullable=False)
    score_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("submission_id", "score_code", name="uq_submission_score_code"),
        Index("idx_assessment_score_submission", "submission_id"),
    )


class AssessmentReview(BusinessBaseMixin, Base):
    """护士从 AI 提交和独立评估形成最终确认的复核记录。"""

    __tablename__ = "assessment_review"

    review_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    assessment_instance_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assessment_instance.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_submission_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("assessment_submission.id", ondelete="RESTRICT"),
        nullable=True,
    )
    nurse_submission_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("assessment_submission.id", ondelete="RESTRICT"),
        nullable=True,
    )
    final_submission_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("assessment_submission.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reviewer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    supplementary_inquiry: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_assessment_review_instance", "assessment_instance_id", "deleted"),
        Index("idx_assessment_review_status", "review_status", "deleted"),
    )
