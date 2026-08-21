"""保存字段抽取单字段失败记录，供医护人工处理。"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260821_extraction_manual"
down_revision: str | Sequence[str] | None = "20260821_standard_answer_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为抽取提交增加人工介入字段快照。"""
    op.add_column(
        "assessment_submission",
        sa.Column(
            "invalid_answers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """删除失败字段快照。"""
    op.drop_column("assessment_submission", "invalid_answers")
