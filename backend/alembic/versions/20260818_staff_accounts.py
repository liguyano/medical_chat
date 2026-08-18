"""新增医护端登录账号表。

Revision ID: 20260818_staff_accounts
Revises: 20260818_quality_review
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260818_staff_accounts"
down_revision: str | Sequence[str] | None = "20260818_quality_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建医护端登录账号表。"""
    op.create_table(
        "staff_account",
        sa.Column(
            "staff_no",
            sa.String(length=64),
            nullable=False,
            comment="医护工号/登录账号",
        ),
        sa.Column(
            "staff_name",
            sa.String(length=128),
            nullable=False,
            comment="医护姓名",
        ),
        sa.Column(
            "role_code",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'nurse'"),
            comment="角色编码：nurse/doctor",
        ),
        sa.Column(
            "department_name",
            sa.String(length=128),
            nullable=True,
            comment="所属科室",
        ),
        sa.Column(
            "password_hash",
            sa.Text(),
            nullable=False,
            comment="密码 bcrypt 哈希",
        ),
        sa.Column(
            "account_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'启用'"),
            comment="账号状态：启用/停用",
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("staff_no"),
    )
    op.create_index(
        "idx_staff_account_status",
        "staff_account",
        ["account_status", "deleted"],
        unique=False,
    )
    op.create_index(
        "idx_staff_account_role",
        "staff_account",
        ["role_code", "deleted"],
        unique=False,
    )


def downgrade() -> None:
    """删除医护端登录账号表。"""
    op.drop_index("idx_staff_account_role", table_name="staff_account")
    op.drop_index("idx_staff_account_status", table_name="staff_account")
    op.drop_table("staff_account")
