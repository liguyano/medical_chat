"""医护账号 ORM 模型。
作用：保存医护端登录账号、展示信息和密码哈希，不保存明文密码。
"""

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class StaffAccount(BusinessBaseMixin, Base):
    """医护端登录账号。"""

    __tablename__ = "staff_account"

    staff_no: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="医护工号/登录账号",
    )
    staff_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="医护姓名",
    )
    role_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="nurse",
        comment="角色编码：nurse/doctor",
    )
    department_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="所属科室",
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="密码 bcrypt 哈希",
    )
    account_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="启用",
        comment="账号状态：启用/停用",
    )

    __table_args__ = (
        Index(
            "idx_staff_account_status",
            "account_status",
            "deleted",
        ),
        Index(
            "idx_staff_account_role",
            "role_code",
            "deleted",
        ),
    )
