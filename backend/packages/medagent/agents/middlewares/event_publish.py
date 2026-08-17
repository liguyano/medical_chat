"""对话事件发布中间件。

事件接收器由应用层注入，SDK 仅产生稳定的事件字典契约。
"""

import inspect
import logging
from typing import Any

from ..service_agent.dialog_agent.models import DialogEventSink
from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class EventPublishMiddleware(DialogMiddleware):
    """对话结束后发布轮次和工具调用事件。"""

    def __init__(
        self,
        session_id: str,
        event_sink: DialogEventSink | None = None,
    ) -> None:
        self.session_id = session_id
        self.event_sink = event_sink

    async def before_agent(self, context: dict[str, Any]) -> None:
        """事件发布在 after 阶段进行。"""

    async def _publish(self, event: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        result = self.event_sink(event)
        if inspect.isawaitable(result):
            await result

    async def after_agent(self, context: dict[str, Any], output: Any) -> None:
        """发布 DialogTurnEvent 和逐条 ToolCallEvent。"""
        try:
            turn_number = int(context.get("turn_number", 0))
            tool_calls = list(context.get("tool_calls") or [])
            await self._publish(
                {
                    "event_type": "dialog_turn",
                    "session_id": self.session_id,
                    "turn_number": turn_number,
                    "question": str(context.get("patient_input", "")),
                    "answer": str(output or ""),
                    "tool_calls": tool_calls or None,
                }
            )
            for tool_call in tool_calls:
                await self._publish(
                    {
                        "event_type": "tool_call",
                        "session_id": self.session_id,
                        "turn_number": turn_number,
                        "tool_name": str(tool_call.get("name", "")),
                        "tool_args": dict(tool_call.get("arguments") or {}),
                        "tool_result": tool_call.get("result"),
                    }
                )
        except Exception:
            logger.exception("[EventPublishMiddleware] 事件发布失败")
