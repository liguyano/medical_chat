"""增加 AI 首问准备状态和患者发布时间。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_task_preparation"
down_revision: str | Sequence[str] | None = "20260821_normalize_type_residue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为护理任务增加后台准备快照，并回填已经激活的历史会话。"""
    op.add_column(
        "care_task",
        sa.Column(
            "preparation_status",
            sa.String(length=32),
            server_default="not_required",
            nullable=False,
            comment="AI首问准备状态：not_required/queued/running/ready/failed",
        ),
    )
    op.add_column(
        "care_task",
        sa.Column(
            "preparation_stage",
            sa.String(length=64),
            nullable=True,
            comment="AI首问准备当前阶段",
        ),
    )
    op.add_column(
        "care_task",
        sa.Column(
            "preparation_error",
            sa.Text(),
            nullable=True,
            comment="AI首问准备失败原因",
        ),
    )
    op.add_column(
        "care_task",
        sa.Column(
            "preparation_attempt",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="AI首问准备重试次数",
        ),
    )
    op.add_column(
        "care_task",
        sa.Column(
            "preparation_detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="AI首问准备阶段快照，仅供医护端查看",
        ),
    )
    op.add_column(
        "care_task",
        sa.Column(
            "patient_visible_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="任务向患者端发布的时间",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE care_task AS task
            SET preparation_status = CASE
                    WHEN task.collection_mode <> 'ai_dialogue' THEN 'not_required'
                    WHEN EXISTS (
                        SELECT 1
                        FROM interaction_session AS session
                        WHERE session.task_id = task.id
                          AND session.session_status = 'active'
                          AND session.deleted = 0
                    ) THEN 'ready'
                    ELSE 'queued'
                END,
                patient_visible_at = CASE
                    WHEN task.collection_mode <> 'ai_dialogue' THEN task.create_time
                    WHEN EXISTS (
                        SELECT 1
                        FROM interaction_session AS session
                        WHERE session.task_id = task.id
                          AND session.session_status = 'active'
                          AND session.deleted = 0
                    ) THEN COALESCE(task.update_time, task.create_time)
                    ELSE NULL
                END
            """
        )
    )


def downgrade() -> None:
    """移除 AI 首问准备字段。"""
    op.drop_column("care_task", "patient_visible_at")
    op.drop_column("care_task", "preparation_detail")
    op.drop_column("care_task", "preparation_attempt")
    op.drop_column("care_task", "preparation_error")
    op.drop_column("care_task", "preparation_stage")
    op.drop_column("care_task", "preparation_status")
