"""新增版本化评估报告

Revision ID: 20260826_assessment_report
Revises: 20260822_patient_portal
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260826_assessment_report"
down_revision: str | Sequence[str] | None = "20260822_patient_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建评估报告版本表。"""
    op.create_table(
        "assessment_report",
        sa.Column("report_no", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("report_status", sa.String(length=32), nullable=False),
        sa.Column("source_submission_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_by", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("creator", sa.String(length=64), nullable=True),
        sa.Column("updator", sa.String(length=64), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_by"], ["staff_account.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["care_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_no"),
        sa.UniqueConstraint("task_id", "version_no", name="uq_assessment_report_task_version"),
    )
    op.create_index(
        "idx_assessment_report_task_created",
        "assessment_report",
        ["task_id", "generated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """删除评估报告版本表。"""
    op.drop_index("idx_assessment_report_task_created", table_name="assessment_report")
    op.drop_table("assessment_report")
