"""关键词匹配器
作用：从 interaction_rule 加载生效规则，对患者文本做精确匹配 + 简单正则匹配，
      多命中按 priority 降序返回，供对话消息拦截使用。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import base as model_base
from app.models.interaction import InteractionRule

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """单条规则命中结果
    作用：承载命中规则的关键信息，供拦截逻辑注入约束提示。
    """

    rule_code: str
    rule_name: str
    action_type: str
    priority: int
    matched_terms: list[str] = field(default_factory=list)
    action_payload: dict = field(default_factory=dict)

    @property
    def constraint_prompt(self) -> str:
        """约束提示词
        Return:
            - action_payload.prompt，缺省为空串
        """
        return str(self.action_payload.get("prompt", ""))


@dataclass
class _CompiledRule:
    """编译后的规则（进程内缓存单元）"""

    rule_code: str
    rule_name: str
    action_type: str
    priority: int
    action_payload: dict
    keywords: list[str]
    patterns: list[re.Pattern]


class KeywordMatcher:
    """关键词匹配器
    作用：加载 interaction_rule 生效规则并缓存，提供文本匹配能力。
    类参数：
        - session_factory: 可选会话工厂；为空时使用全局 SessionLocal
    """

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory
        self._rules: list[_CompiledRule] | None = None
        self._lock = Lock()

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    def load_rules(self, force: bool = False) -> list[_CompiledRule]:
        """加载并缓存生效规则
        作用：首次调用或 force=True 时从库加载 status='active' 的规则并编译正则；
              否则复用进程内缓存，避免每次查库。
        Args:
            - force: 是否强制刷新缓存
        Return:
            - 已编译规则列表（按 priority 降序）
        """
        if self._rules is not None and not force:
            return self._rules

        with self._lock:
            if self._rules is not None and not force:
                return self._rules

            with self._new_session() as db:
                rows = list(
                    db.scalars(
                        select(InteractionRule)
                        .where(
                            InteractionRule.status == "active",
                            InteractionRule.deleted == 0,
                        )
                        .order_by(InteractionRule.priority.desc())
                    ).all()
                )

            compiled: list[_CompiledRule] = []
            for row in rows:
                condition = row.trigger_condition or {}
                keywords = [str(k) for k in condition.get("keywords", [])]
                patterns: list[re.Pattern] = []
                for raw in condition.get("patterns", []):
                    try:
                        patterns.append(re.compile(str(raw)))
                    except re.error as e:
                        logger.warning(
                            "规则 %s 正则编译失败，已跳过: %s -> %s", row.rule_code, raw, e
                        )
                compiled.append(
                    _CompiledRule(
                        rule_code=row.rule_code,
                        rule_name=row.rule_name,
                        action_type=row.action_type,
                        priority=row.priority,
                        action_payload=row.action_payload or {},
                        keywords=keywords,
                        patterns=patterns,
                    )
                )

            self._rules = compiled
            logger.info("关键词规则加载完成: %s 条生效规则", len(compiled))
            return self._rules

    def match(self, text: str | None) -> list[MatchResult]:
        """对文本执行匹配
        作用：每次从数据库刷新规则后执行关键词 + 正则匹配，保证 Demo 配置中心
              的修改在 API 与不同 Celery Worker 进程中立即生效。
        Args:
            - text: 待匹配文本（患者输入）
        Return:
            - 命中结果列表，未命中返回空列表
        """
        if not text:
            return []

        rules = self.load_rules(force=True)
        results: list[MatchResult] = []

        for rule in rules:
            matched_terms: list[str] = []
            # 精确匹配
            for keyword in rule.keywords:
                if keyword and keyword in text:
                    matched_terms.append(keyword)
            # 正则匹配
            for pattern in rule.patterns:
                found = pattern.search(text)
                if found:
                    matched_terms.append(found.group(0))

            if matched_terms:
                results.append(
                    MatchResult(
                        rule_code=rule.rule_code,
                        rule_name=rule.rule_name,
                        action_type=rule.action_type,
                        priority=rule.priority,
                        matched_terms=matched_terms,
                        action_payload=rule.action_payload,
                    )
                )

        # 已按规则优先级排序，命中列表保持降序
        return results


# 进程内单例，避免每次请求重新加载规则
_matcher: KeywordMatcher | None = None
_matcher_lock = Lock()


def get_keyword_matcher() -> KeywordMatcher:
    """获取全局关键词匹配器单例
    Return:
        - KeywordMatcher 实例
    """
    global _matcher
    if _matcher is None:
        with _matcher_lock:
            if _matcher is None:
                _matcher = KeywordMatcher()
    return _matcher
