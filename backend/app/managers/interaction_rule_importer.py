"""关键词规则导入器
作用：将 backend/app/data/keyword_library.json 幂等导入 interaction_rule 表，
      供 KeywordMatcher 加载使用。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import base as model_base
from app.models.interaction import InteractionRule

logger = logging.getLogger(__name__)

# 默认种子文件路径：app/data/keyword_library.json
_DEFAULT_LIBRARY = Path(__file__).resolve().parent.parent / "data" / "keyword_library.json"


class InteractionRuleImporter:
    """关键词规则幂等导入器
    作用：按 rule_code 幂等 upsert 关键词规则到 interaction_rule。
    类参数：
        - session_factory: 可选会话工厂；为空时使用全局 SessionLocal
    """

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    def import_from_file(self, path: Path | str | None = None) -> dict[str, int]:
        """从 JSON 文件导入关键词规则
        Args:
            - path: 规则文件路径，缺省使用 app/data/keyword_library.json
        Return:
            - 统计字典 {created, updated, total}
        """
        library_path = Path(path) if path else _DEFAULT_LIBRARY
        with open(library_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        rules = payload.get("rules", [])
        created = 0
        updated = 0

        with self._new_session() as db:
            try:
                for rule in rules:
                    if self._upsert_rule(db, rule):
                        created += 1
                    else:
                        updated += 1
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("导入关键词规则失败: %s", library_path)
                raise

        logger.info(
            "关键词规则导入完成: created=%s updated=%s total=%s", created, updated, len(rules)
        )
        return {"created": created, "updated": updated, "total": len(rules)}

    @staticmethod
    def _upsert_rule(db: Session, rule: dict) -> bool:
        """按 rule_code 幂等写入单条规则
        Args:
            - db: 数据库会话
            - rule: 规则字典
        Return:
            - bool: True 表示新建，False 表示更新
        """
        existing = db.execute(
            select(InteractionRule).where(
                InteractionRule.rule_code == rule["rule_code"]
            )
        ).scalar_one_or_none()

        if existing is None:
            db.add(
                InteractionRule(
                    rule_code=rule["rule_code"],
                    rule_name=rule["rule_name"],
                    scope_type=rule.get("scope_type", "global"),
                    scope_id=rule.get("scope_id"),
                    trigger_condition=rule["trigger_condition"],
                    action_type=rule["action_type"],
                    action_payload=rule["action_payload"],
                    priority=rule.get("priority", 0),
                    status=rule.get("status", "active"),
                    creator="system",
                )
            )
            return True

        # 更新既有规则内容（保持幂等）
        existing.rule_name = rule["rule_name"]
        existing.scope_type = rule.get("scope_type", "global")
        existing.scope_id = rule.get("scope_id")
        existing.trigger_condition = rule["trigger_condition"]
        existing.action_type = rule["action_type"]
        existing.action_payload = rule["action_payload"]
        existing.priority = rule.get("priority", 0)
        existing.status = rule.get("status", "active")
        existing.updator = "system"
        return False
