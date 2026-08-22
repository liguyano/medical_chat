"""生产环境初始化命令。

作用：迁移完成后导入量表和交互规则，并按显式环境变量创建首个医护账号。
本命令不会创建演示患者，也不会使用演示账号或默认密码。

用法：
    BOOTSTRAP_STAFF_NO=... \
    BOOTSTRAP_STAFF_NAME=... \
    BOOTSTRAP_STAFF_PASSWORD=... \
    uv run python -m app.commands.bootstrap_production
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import select

from app.configs.app_config import get_app_config
from app.managers.assessment_catalog_importer import AssessmentCatalogImporter
from app.managers.interaction_rule_importer import InteractionRuleImporter
from app.models import base as model_base
from app.models.base import init_db
from app.models.staff_account import StaffAccount
from app.utils.password import hash_password


def _required_env(name: str) -> str:
    """读取必填初始化环境变量，不在错误中输出实际密钥。"""
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"缺少必填环境变量: {name}")
    return value


def _upsert_staff() -> str:
    """幂等创建首个生产医护账号。"""
    staff_no = _required_env("BOOTSTRAP_STAFF_NO")
    staff_name = _required_env("BOOTSTRAP_STAFF_NAME")
    password = _required_env("BOOTSTRAP_STAFF_PASSWORD")
    if len(password) < 12:
        raise SystemExit("BOOTSTRAP_STAFF_PASSWORD 至少需要 12 位")

    role_code = os.getenv("BOOTSTRAP_STAFF_ROLE", "nurse").strip() or "nurse"
    department_name = os.getenv("BOOTSTRAP_STAFF_DEPARTMENT", "").strip() or None
    if model_base.SessionLocal is None:
        raise RuntimeError("数据库未初始化")

    with model_base.SessionLocal() as db:
        staff = db.scalar(
            select(StaffAccount).where(
                StaffAccount.staff_no == staff_no,
                StaffAccount.deleted == 0,
            )
        )
        if staff is None:
            db.add(
                StaffAccount(
                    staff_no=staff_no,
                    staff_name=staff_name,
                    role_code=role_code,
                    department_name=department_name,
                    password_hash=hash_password(password),
                    account_status="启用",
                    creator="bootstrap",
                    updator="bootstrap",
                )
            )
            db.commit()
            return "created"

        if os.getenv("BOOTSTRAP_ROTATE_PASSWORD", "").lower() == "true":
            staff.password_hash = hash_password(password)
        staff.staff_name = staff_name
        staff.role_code = role_code
        staff.department_name = department_name
        staff.account_status = "启用"
        staff.deleted = 0
        staff.updator = "bootstrap"
        db.commit()
        return "updated"


def main() -> None:
    """执行生产数据初始化。"""
    parser = argparse.ArgumentParser(description="初始化生产量表、规则和首个医护账号")
    parser.add_argument(
        "--scales-directory",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "docs"
        / "structured"
        / "assessment-scales",
        help="结构化量表目录",
    )
    parser.add_argument(
        "--skip-catalog",
        action="store_true",
        help="跳过量表和交互规则导入",
    )
    args = parser.parse_args()

    config = get_app_config()
    init_db(
        config.database.url,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        pool_pre_ping=config.database.pool_pre_ping,
        echo=config.database.echo,
    )

    result: dict[str, object] = {"staff": _upsert_staff()}
    if not args.skip_catalog:
        result["scales"] = AssessmentCatalogImporter().import_directory(
            args.scales_directory,
            publish_status="已发布",
        )
        result["rules"] = InteractionRuleImporter().import_from_file()
    print(result)


if __name__ == "__main__":
    main()
