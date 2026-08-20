"""宣教模板域 ORM 模型
作用：定义 Demo 配置中心直接维护的宣教方案、版本和内容单元。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class EducationProgram(BusinessBaseMixin, Base):
    """宣教方案主档。"""

    __tablename__ = "education_program"

    program_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    program_name: Mapped[str] = mapped_column(String(128), nullable=False)
    education_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    program_type: Mapped[str] = mapped_column(String(32), nullable=False)
    applicable_department: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    applicable_disease_tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    __table_args__ = (Index("idx_education_program_status", "status", "deleted"),)


class EducationProgramVersion(BusinessBaseMixin, Base):
    """宣教方案当前可执行版本。"""

    __tablename__ = "education_program_version"

    program_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("education_program.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    publish_status: Mapped[str] = mapped_column(String(32), nullable=False, default="published")
    effective_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("program_id", "version_code", name="uq_education_version_code"),
        Index("idx_education_version_program", "program_id", "deleted"),
    )


class EducationUnit(BusinessBaseMixin, Base):
    """可展示、可播报的宣教内容单元。"""

    __tablename__ = "education_unit"

    program_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("education_program_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_unit_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unit_code: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_title: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(64), nullable=False, default="risk_warning")
    original_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    patient_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mandatory: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    teachback_required: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="important")
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "program_version_id",
            "unit_code",
            name="uq_education_unit_code",
        ),
        Index("idx_education_unit_version", "program_version_id", "sort_no"),
    )
