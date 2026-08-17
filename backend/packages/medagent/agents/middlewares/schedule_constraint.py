"""调度约束中间件。

约束来源由应用层注入，SDK 不感知 Redis Stream 的具体实现。
"""

import inspect
import logging
from typing import Any

from ..service_agent.dialog_agent.models import ConstraintSource
from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class ScheduleConstraintMiddleware(DialogMiddleware):
    """读取 Schedule Agent 约束并注入当前上下文。"""

    def __init__(self, constraint_source: ConstraintSource | None = None) -> None:
        self.constraint_source = constraint_source

    async def before_agent(self, context: dict[str, Any]) -> None:
        """读取当前会话尚未消费的约束。"""
        session_id = context.get("session_id")
        if not session_id or self.constraint_source is None:
            return

        try:
            result = self.constraint_source(str(session_id))
            constraints = await result if inspect.isawaitable(result) else result
            target = context.setdefault("constraints", [])
            target.extend(item for item in constraints if item and item not in target)
        except Exception:
            logger.exception("[ScheduleConstraintMiddleware] 读取约束失败")

    async def after_agent(self, context: dict[str, Any], output: Any) -> None:
        """调度约束无需 after 处理。"""
