"""清理数据库快照和答案中的历史类型残留。"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260821_normalize_type_residue"
down_revision: str | Sequence[str] | None = "20260821_extraction_manual"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """确保任何持久化位置都只保留标准多选类型。"""
    for source in (
        "multi_choice_with_other",
        "multi_choice_with_detail",
        "multi_choice",
    ):
        op.execute(
            sa.text(
                "UPDATE assessment_answer SET answer_type = 'multiple_choice' "
                "WHERE answer_type = :source"
            ).bindparams(source=source)
        )
        op.execute(
            sa.text(
                "UPDATE assessment_scale_version "
                "SET scale_snapshot = replace(scale_snapshot::text, "
                ":quoted_source, '\"multiple_choice\"')::jsonb "
                "WHERE scale_snapshot::text LIKE :pattern"
            ).bindparams(
                quoted_source=f'"{source}"',
                pattern=f"%{source}%",
            )
        )


def downgrade() -> None:
    """清理迁移不可逆。"""
    raise RuntimeError("历史类型残留清理不支持回滚")
