"""患者与护理任务域 ORM 模型
作用：定义患者、住院记录和护理任务三张核心业务表。
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class Patient(BusinessBaseMixin, Base):
    """患者主档。"""

    __tablename__ = "patient"

    patient_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="系统患者唯一编号")
    his_patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="HIS患者主索引")
    patient_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="患者姓名")
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="性别")
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="联系方式")
    id_card_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True, comment="加密后的身份证号")
    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="紧急联系人姓名"
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="紧急联系人关系"
    )
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="紧急联系人电话"
    )
    address: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="常住地址"
    )

    __table_args__ = (
        Index("idx_patient_name", "patient_name"),
        Index("idx_patient_deleted", "deleted"),
    )


class PatientEncounter(BusinessBaseMixin, Base):
    """患者一次住院记录。"""

    __tablename__ = "patient_encounter"

    encounter_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="住院过程编号")
    patient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient.id", ondelete="RESTRICT"),
        nullable=False,
        comment="患者ID",
    )
    inpatient_no: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="医院住院号")
    department_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="科室编码")
    department_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="科室名称快照")
    ward_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="病区")
    bed_no: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="床号")
    admission_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入院时间")
    discharge_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="出院时间")
    diagnosis_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="诊断快照")
    encounter_status: Mapped[str] = mapped_column(String(32), nullable=False, comment="住院状态")
    admission_source: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="入院来源"
    )
    nursing_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="护理级别"
    )
    insurance_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="医保或费用类别"
    )
    allergy_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="过敏史安全摘要"
    )

    __table_args__ = (
        Index("idx_patient_encounter_patient", "patient_id", "deleted"),
        Index("idx_patient_encounter_status", "encounter_status", "deleted"),
    )


class CareTask(BusinessBaseMixin, Base):
    """护理任务，需求业务流程根对象。"""

    __tablename__ = "care_task"

    task_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="任务编号")
    patient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient.id", ondelete="RESTRICT"),
        nullable=False,
        comment="患者ID",
    )
    encounter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient_encounter.id", ondelete="RESTRICT"),
        nullable=False,
        comment="住院记录ID",
    )
    parent_task_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("care_task.id", ondelete="RESTRICT"),
        nullable=True,
        comment="父任务ID",
    )
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="任务类型")
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    task_source: Mapped[str] = mapped_column(String(32), nullable=False, comment="任务来源")
    collection_mode: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="采集模式：traditional_form或ai_dialogue；子任务从父任务继承",
    )
    task_status: Mapped[str] = mapped_column(String(32), nullable=False, comment="任务状态")
    assigned_nurse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="负责护士ID")
    planned_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    need_manual_intervention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    intervention_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_care_task_patient", "patient_id", "deleted"),
        Index("idx_care_task_encounter", "encounter_id", "deleted"),
        Index("idx_care_task_status", "task_status", "deleted"),
        Index("idx_care_task_parent", "parent_task_id"),
    )
