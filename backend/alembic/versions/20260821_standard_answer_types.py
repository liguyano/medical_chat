"""统一量表问题和结构化答案类型为标准英文值。"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260821_standard_answer_types"
down_revision: str | Sequence[str] | None = "20260820_patient_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """把现存演示数据一次性转换为唯一标准类型。"""
    question_map = {
        "文本": "text",
        "数字": "number",
        "布尔": "boolean",
        "日期": "date",
        "日期时间": "date",
        "单选": "single_choice",
        "多选": "multiple_choice",
    }
    value_map = {
        "字符串": "string",
        "整数": "number",
        "小数": "number",
        "布尔": "boolean",
        "日期": "date",
        "日期时间": "date",
    }
    for source, target in question_map.items():
        op.execute(
            sa.text(
                "UPDATE assessment_question SET question_type = :target "
                "WHERE question_type = :source"
            ).bindparams(source=source, target=target)
        )
    for source, target in value_map.items():
        op.execute(
            sa.text(
                "UPDATE assessment_question SET value_type = :target "
                "WHERE value_type = :source"
            ).bindparams(source=source, target=target)
        )
    for source, target in question_map.items():
        op.execute(
            sa.text(
                "UPDATE assessment_answer SET answer_type = :target "
                "WHERE answer_type = :source"
            ).bindparams(source=source, target=target)
        )


def downgrade() -> None:
    """标准类型不可逆回滚，避免重新引入已清除的历史别名。"""
    raise RuntimeError("标准答案类型迁移不支持回滚")
