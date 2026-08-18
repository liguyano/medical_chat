"""Dialog Agent 依赖协议与通用类型。

本模块只描述 SDK 所需能力，不依赖具体数据库、Redis 或应用层实现。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class DialogStateStore(Protocol):
    """Dialog Agent 异步状态存储协议。"""

    async def save_agent_state(
        self,
        session_id: str,
        agent_state: dict[str, Any],
    ) -> bool:
        """保存会话状态。"""


class DialogHistoryStore(Protocol):
    """Dialog Agent 对话历史存储协议。"""

    async def save_message(
        self,
        session_no: str,
        *,
        turn_no: int,
        role_type: str,
        message_type: str,
        content_text: str | None = None,
        asr_text: str | None = None,
        tts_text: str | None = None,
    ) -> Any:
        """保存一条患者或 AI 消息。"""


ConstraintSource = Callable[[str], list[str] | Awaitable[list[str]]]
DialogEventSink = Callable[[dict[str, Any]], Any | Awaitable[Any]]
ActivityUpdater = Callable[[str], bool | Awaitable[bool]]
DialogToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]
DialogTextDeltaSink = Callable[[str, dict[str, Any]], Awaitable[None]]
