"""患者画像与护理计划 ORM 模型
作用：保存评估结果生成的患者画像快照、护理计划及计划明细。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class PatientProfileSnapshot(BusinessBaseMixin, Base):
    """某次评估结果对应的患者画像快照。"""

    __tablename__ = "patient_profile_snapshot"

    profile_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
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
    source_submission_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    cooperation_level: Mapped[str] = mapped_column(String(32), nullable=False)
    cognition_level: Mapped[str] = mapped_column(String(32), nullable=False)
    self_care_level: Mapped[str] = mapped_column(String(32), nullable=False)
    fall_risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    pressure_risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    nutrition_risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    communication_level: Mapped[str] = mapped_column(String(32), nullable=False)
    education_need_level: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_patient_profile_encounter",
            "patient_id",
            "encounter_id",
            "generated_at",
        ),
    )


class NursingPlan(BusinessBaseMixin, Base):
    """基于患者画像生成并由护士确认的护理计划。"""

    __tablename__ = "nursing_plan"

    plan_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
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
    profile_snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient_profile_snapshot.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_summary: Mapped[str] = mapped_column(Text, nullable=False)
    education_summary: Mapped[str] = mapped_column(Text, nullable=False)
    handover_summary: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("staff_account.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "idx_nursing_plan_encounter_status",
            "patient_id",
            "encounter_id",
            "plan_status",
        ),
        Index("idx_nursing_plan_profile", "profile_snapshot_id"),
    )


class NursingPlanItem(BusinessBaseMixin, Base):
    """护理计划中的一条结构化指导建议。"""

    __tablename__ = "nursing_plan_item"

    nursing_plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("nursing_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    item_content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    nurse_action: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
    )
    nurse_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "idx_nursing_plan_item_plan",
            "nursing_plan_id",
            "priority",
            "id",
        ),
    )
