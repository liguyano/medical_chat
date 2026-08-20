"""扩展患者管理字段并增加交互事件调用幂等键。

Revision ID: 20260820_patient_event
Revises: 20260820_nursing_plan
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_patient_event"
down_revision: str | Sequence[str] | None = "20260820_nursing_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加患者管理和工具调用身份字段。"""
    op.add_column(
        "patient",
        sa.Column("emergency_contact_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "patient",
        sa.Column("emergency_contact_relation", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "patient",
        sa.Column("emergency_contact_phone", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "patient",
        sa.Column("address", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "patient_encounter",
        sa.Column("admission_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "patient_encounter",
        sa.Column("nursing_level", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "patient_encounter",
        sa.Column("insurance_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "patient_encounter",
        sa.Column("allergy_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "interaction_event",
        sa.Column(
            "source_invocation_id",
            sa.String(length=160),
            nullable=True,
            comment="同一会话内的来源调用编号，用于重复交付幂等",
        ),
    )
    op.create_index(
        "uq_interaction_event_source_invocation",
        "interaction_event",
        ["interaction_session_id", "source_invocation_id"],
        unique=True,
    )


def downgrade() -> None:
    """移除患者管理和工具调用身份字段。"""
    op.drop_index(
        "uq_interaction_event_source_invocation",
        table_name="interaction_event",
    )
    op.drop_column("interaction_event", "source_invocation_id")
    op.drop_column("patient_encounter", "allergy_summary")
    op.drop_column("patient_encounter", "insurance_type")
    op.drop_column("patient_encounter", "nursing_level")
    op.drop_column("patient_encounter", "admission_source")
    op.drop_column("patient", "address")
    op.drop_column("patient", "emergency_contact_phone")
    op.drop_column("patient", "emergency_contact_relation")
    op.drop_column("patient", "emergency_contact_name")
