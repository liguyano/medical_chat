"""增加嵌入式设备任务分配。"""

from alembic import op
import sqlalchemy as sa

revision = "20261111_embedded_device"
down_revision = "20260826_assessment_report"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("care_task", sa.Column("device_id", sa.String(64), nullable=True))
    op.create_index(
        "uq_care_task_active_device",
        "care_task",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text(
            "device_id IS NOT NULL AND deleted = 0 AND task_status IN ('pending', 'in_progress', 'pending_review')"
        ),
    )


def downgrade():
    op.drop_index("uq_care_task_active_device", table_name="care_task")
    op.drop_column("care_task", "device_id")
