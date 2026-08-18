"""演示医护账号种子导入器。
作用：幂等写入多组医护端演示账号，数据库只保存 bcrypt 密码哈希。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import base as model_base
from app.models.staff_account import StaffAccount
from app.utils.password import hash_password, verify_password

logger = logging.getLogger(__name__)

_STAFF_SEEDS: list[dict[str, str]] = [
    {
        "staff_no": "N001",
        "staff_name": "李护士",
        "role_code": "nurse",
        "department_name": "心内科",
        "password": "123456",
    },
    {
        "staff_no": "N002",
        "staff_name": "王护士",
        "role_code": "nurse",
        "department_name": "老年医学科",
        "password": "123456",
    },
    {
        "staff_no": "N003",
        "staff_name": "赵护士",
        "role_code": "nurse",
        "department_name": "消化内科",
        "password": "123456",
    },
    {
        "staff_no": "N004",
        "staff_name": "陈护士",
        "role_code": "nurse",
        "department_name": "呼吸与危重症医学科",
        "password": "123456",
    },
    {
        "staff_no": "N005",
        "staff_name": "刘护士",
        "role_code": "nurse",
        "department_name": "骨科",
        "password": "123456",
    },
]


class StaffSeeder:
    """演示医护账号幂等种子导入器。"""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    def seed(self) -> dict[str, int]:
        """幂等写入医护账号。

        Return:
            - 统计字典 {created, updated, total}
        """
        stats = {
            "created": 0,
            "updated": 0,
            "total": len(_STAFF_SEEDS),
        }
        with self._new_session() as db:
            try:
                for seed in _STAFF_SEEDS:
                    existing = db.scalar(
                        select(StaffAccount).where(
                            StaffAccount.staff_no == seed["staff_no"],
                        )
                    )
                    if existing is None:
                        db.add(
                            StaffAccount(
                                staff_no=seed["staff_no"],
                                staff_name=seed["staff_name"],
                                role_code=seed["role_code"],
                                department_name=seed["department_name"],
                                password_hash=hash_password(seed["password"]),
                                account_status="启用",
                                creator="seed",
                                updator="seed",
                            )
                        )
                        stats["created"] += 1
                        continue

                    existing.staff_name = seed["staff_name"]
                    existing.role_code = seed["role_code"]
                    existing.department_name = seed["department_name"]
                    existing.account_status = "启用"
                    existing.deleted = 0
                    if not verify_password(seed["password"], existing.password_hash):
                        existing.password_hash = hash_password(seed["password"])
                    existing.updator = "seed"
                    stats["updated"] += 1
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("演示医护账号种子导入失败")
                raise

        logger.info("演示医护账号种子导入完成: %s", stats)
        return stats
