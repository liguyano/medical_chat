"""新增护士逐条消息质评与整体 AI 质量评价域。

Revision ID: 20260818_quality_review
Revises: 26533d4669bd
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260818_quality_review"
down_revision: str | Sequence[str] | None = "26533d4669bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _business_columns() -> list[sa.Column]:
    """返回质量评价表共用审计字段。"""
    return [
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "creator",
            sa.String(length=64),
            nullable=True,
            comment="创建人账号或系统标识",
        ),
        sa.Column(
            "updator",
            sa.String(length=64),
            nullable=True,
            comment="最后更新人账号或系统标识",
        ),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="更新时间",
        ),
        sa.Column(
            "deleted",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="逻辑删除：0未删除，1已删除",
        ),
    ]


def upgrade() -> None:
    """升级数据库结构。"""
    op.add_column(
        "interaction_message_feedback",
        sa.Column(
            "score",
            sa.Integer(),
            nullable=True,
            comment="护士对单条 AI 消息的 1～5 分质量评价",
        ),
    )
    op.create_check_constraint(
        "ck_message_feedback_score",
        "interaction_message_feedback",
        "score IS NULL OR score BETWEEN 1 AND 5",
    )

    op.create_table(
        "quality_review_template",
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("template_name", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("score_scale", sa.String(length=32), nullable=False),
        sa.Column("version_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *_business_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_code",
            "version_code",
            name="uq_quality_review_template_code",
        ),
    )
    op.create_index(
        "idx_quality_review_template_target",
        "quality_review_template",
        ["target_type", "status", "deleted"],
        unique=False,
    )

    op.create_table(
        "quality_review_dimension",
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension_code", sa.String(length=64), nullable=False),
        sa.Column("dimension_name", sa.String(length=128), nullable=False),
        sa.Column("dimension_description", sa.String(length=500), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("sort_no", sa.Integer(), nullable=False),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["quality_review_template.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "dimension_code",
            name="uq_quality_review_dimension_code",
        ),
    )
    op.create_index(
        "idx_quality_review_dimension_template",
        "quality_review_dimension",
        ["template_id", "deleted"],
        unique=False,
    )

    op.create_table(
        "quality_review",
        sa.Column("review_no", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), nullable=False),
        sa.Column("reviewer_id", sa.BigInteger(), nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column(
            "issue_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["quality_review_template.id"],
            ondelete="RESTRICT",
        ),
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
        sa.UniqueConstraint("review_no"),
    )
    op.create_index(
        "idx_quality_review_target_reviewer",
        "quality_review",
        ["target_type", "target_id", "reviewer_id", "deleted"],
        unique=False,
    )
    op.create_index(
        "idx_quality_review_patient",
        "quality_review",
        ["patient_id", "encounter_id", "deleted"],
        unique=False,
    )

    op.create_table(
        "quality_review_score",
        sa.Column("quality_review_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension_id", sa.BigInteger(), nullable=False),
        sa.Column("score_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("score_comment", sa.Text(), nullable=False),
        sa.Column(
            "evidence_message_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "evidence_question_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["quality_review_id"],
            ["quality_review.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dimension_id"],
            ["quality_review_dimension.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quality_review_id",
            "dimension_id",
            name="uq_quality_review_score_dimension",
        ),
    )
    op.create_index(
        "idx_quality_review_score_review",
        "quality_review_score",
        ["quality_review_id", "deleted"],
        unique=False,
    )


def downgrade() -> None:
    """回滚数据库结构。"""
    op.drop_index("idx_quality_review_score_review", table_name="quality_review_score")
    op.drop_table("quality_review_score")

    op.drop_index("idx_quality_review_patient", table_name="quality_review")
    op.drop_index("idx_quality_review_target_reviewer", table_name="quality_review")
    op.drop_table("quality_review")

    op.drop_index(
        "idx_quality_review_dimension_template",
        table_name="quality_review_dimension",
    )
    op.drop_table("quality_review_dimension")

    op.drop_index(
        "idx_quality_review_template_target",
        table_name="quality_review_template",
    )
    op.drop_table("quality_review_template")

    op.drop_constraint(
        "ck_message_feedback_score",
        "interaction_message_feedback",
        type_="check",
    )
    op.drop_column("interaction_message_feedback", "score")
