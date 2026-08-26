"""评估报告 ORM 模型
作用：按护理任务保存可追溯、可重复查看的 LLM 评估报告版本。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class AssessmentReport(BusinessBaseMixin, Base):
    """一次护理任务的一个评估报告版本。"""

    __tablename__ = "assessment_report"

    report_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("care_task.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    report_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="generated"
    )
    source_submission_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    report_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("staff_account.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("task_id", "version_no", name="uq_assessment_report_task_version"),
        Index("idx_assessment_report_task_created", "task_id", "generated_at", "id"),
    )
