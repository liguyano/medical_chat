"""会话活动时间更新中间件。"""

import inspect
import logging
from typing import Any

from ..service_agent.dialog_agent.models import ActivityUpdater
from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class TimeoutMiddleware(DialogMiddleware):
    """对话前后调用应用层注入的活动时间更新器。"""

    def __init__(self, activity_updater: ActivityUpdater | None = None) -> None:
        self.activity_updater = activity_updater

    async def _update(self, session_id: str) -> None:
        if self.activity_updater is None:
            return
        result = self.activity_updater(session_id)
        if inspect.isawaitable(result):
            await result

    async def before_agent(self, context: dict[str, Any]) -> None:
        session_id = context.get("session_id")
        if not session_id:
            return
        try:
            await self._update(str(session_id))
        except Exception:
            logger.exception("[TimeoutMiddleware] 更新活动时间失败")

    async def after_agent(self, context: dict[str, Any], output: Any) -> None:
        session_id = context.get("session_id")
        if not session_id:
            return
        try:
            await self._update(str(session_id))
        except Exception:
            logger.exception("[TimeoutMiddleware] 更新活动时间失败")
