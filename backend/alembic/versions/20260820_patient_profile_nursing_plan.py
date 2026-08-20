"""新增患者画像与护理计划表。

Revision ID: 20260820_nursing_plan
Revises: 20260820_demo_config
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260820_nursing_plan"
down_revision: str | Sequence[str] | None = "20260820_demo_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _business_columns() -> list[sa.Column]:
    """返回领域表统一业务字段。"""
    return [
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("creator", sa.String(length=64), nullable=True),
        sa.Column("updator", sa.String(length=64), nullable=True),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "deleted",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """创建患者画像、护理计划与计划明细表。"""
    op.create_table(
        "patient_profile_snapshot",
        sa.Column("profile_no", sa.String(length=64), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_submission_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("cooperation_level", sa.String(length=32), nullable=False),
        sa.Column("cognition_level", sa.String(length=32), nullable=False),
        sa.Column("self_care_level", sa.String(length=32), nullable=False),
        sa.Column("fall_risk_level", sa.String(length=32), nullable=False),
        sa.Column("pressure_risk_level", sa.String(length=32), nullable=False),
        sa.Column("nutrition_risk_level", sa.String(length=32), nullable=False),
        sa.Column("communication_level", sa.String(length=32), nullable=False),
        sa.Column("education_need_level", sa.String(length=32), nullable=False),
        sa.Column(
            "profile_detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("generated_by", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["patient_encounter.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_no"),
    )
    op.create_index(
        "idx_patient_profile_encounter",
        "patient_profile_snapshot",
        ["patient_id", "encounter_id", "generated_at"],
        unique=False,
    )

    op.create_table(
        "nursing_plan",
        sa.Column("plan_no", sa.String(length=64), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_status", sa.String(length=32), nullable=False),
        sa.Column("risk_summary", sa.Text(), nullable=False),
        sa.Column("education_summary", sa.Text(), nullable=False),
        sa.Column("handover_summary", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(length=32), nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patient.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["patient_encounter.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profile_snapshot_id"],
            ["patient_profile_snapshot.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["staff_account.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_no"),
    )
    op.create_index(
        "idx_nursing_plan_encounter_status",
        "nursing_plan",
        ["patient_id", "encounter_id", "plan_status"],
        unique=False,
    )
    op.create_index(
        "idx_nursing_plan_profile",
        "nursing_plan",
        ["profile_snapshot_id"],
        unique=False,
    )

    op.create_table(
        "nursing_plan_item",
        sa.Column("nursing_plan_id", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("item_code", sa.String(length=64), nullable=False),
        sa.Column("item_content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column(
            "nurse_action",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("nurse_comment", sa.Text(), nullable=True),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["nursing_plan_id"],
            ["nursing_plan.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_nursing_plan_item_plan",
        "nursing_plan_item",
        ["nursing_plan_id", "priority", "id"],
        unique=False,
    )


def downgrade() -> None:
    """删除患者画像与护理计划表。"""
    op.drop_index(
        "idx_nursing_plan_item_plan",
        table_name="nursing_plan_item",
    )
    op.drop_table("nursing_plan_item")
    op.drop_index("idx_nursing_plan_profile", table_name="nursing_plan")
    op.drop_index(
        "idx_nursing_plan_encounter_status",
        table_name="nursing_plan",
    )
    op.drop_table("nursing_plan")
    op.drop_index(
        "idx_patient_profile_encounter",
        table_name="patient_profile_snapshot",
    )
    op.drop_table("patient_profile_snapshot")
