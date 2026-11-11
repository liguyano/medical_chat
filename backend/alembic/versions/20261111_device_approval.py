"""新增嵌入式设备登记与审批记录。"""

import sqlalchemy as sa
from alembic import op

revision = "20261111_device_approval"
down_revision = "20261111_embedded_device"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_registration",
        sa.Column("device_id", sa.String(64), primary_key=True),
        sa.Column("secret_digest", sa.String(64), nullable=False),
        sa.Column("verification_code", sa.String(8), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.BigInteger()),
    )


def downgrade():
    op.drop_table("device_registration")
