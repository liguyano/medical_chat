"""阿里云百炼 Qwen 实时语音 WebSocket 客户端。

作用：封装 Qwen-Audio-Realtime / Qwen-Omni-Realtime 的事件协议，向应用层
提供与供应商无关的发送方法和原始事件异步流。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


def _with_model_query(websocket_url: str, model: str) -> str:
    """按百炼 Realtime 约定把模型名称放入 URL 查询参数。"""
    parts = urlsplit(websocket_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("model", model)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


class QwenRealtimeClient:
    """Qwen Realtime WebSocket 协议适配器。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        websocket_url: str,
        voice: str = "longanqian",
        timeout: float = 30.0,
        connector: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.websocket_url = websocket_url
        self.voice = voice
        self.timeout = timeout
        self.connector = connector or websockets.connect
        self.websocket: Any | None = None
        self.instructions = ""
        self.tools: list[dict[str, Any]] = []

    async def connect(
        self,
        *,
        instructions: str,
        tools: list[dict[str, Any]],
        turn_detection: str | None = None,
        vad_threshold: float = 0.1,
        silence_duration_ms: int = 900,
        max_history_turns: int = 50,
    ) -> None:
        """建立上游连接并发送会话配置。"""
        self.instructions = instructions
        self.tools = list(tools)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-dashscope-dataInspection": "disable",
        }
        websocket_url = _with_model_query(self.websocket_url, self.model)
        try:
            self.websocket = await self.connector(
                websocket_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                open_timeout=self.timeout,
            )
        except TypeError as exc:
            # websockets 12/13 使用 extra_headers，14+ 使用 additional_headers。
            if "additional_headers" not in str(exc):
                raise
            self.websocket = await self.connector(
                websocket_url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                open_timeout=self.timeout,
            )
        session: dict[str, Any] = {
            "modalities": ["text", "audio"],
            "voice": self.voice,
            "instructions": instructions,
            "input_audio_format": "pcm",
            "output_audio_format": "pcm",
            "turn_detection": (
                None
                if turn_detection in {None, "manual", "push_to_talk"}
                else (
                    {
                        "type": "server_vad",
                        "threshold": vad_threshold,
                        "silence_duration_ms": silence_duration_ms,
                    }
                    if turn_detection == "server_vad"
                    else {"type": turn_detection}
                )
            ),
            "tools": tools,
            "max_history_turns": max_history_turns,
        }
        await self.send({"type": "session.update", "session": session})

    async def send(self, payload: dict[str, Any]) -> None:
        """发送 JSON 事件。"""
        if self.websocket is None:
            raise RuntimeError("Qwen 实时连接尚未建立")
        event = dict(payload)
        event.setdefault(
            "event_id",
            f"event_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
        )
        await self.websocket.send(json.dumps(event, ensure_ascii=False))

    async def append_audio(self, audio: bytes) -> None:
        """追加 16kHz PCM16 音频。"""
        import base64

        await self.send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio).decode("ascii"),
            }
        )

    async def commit_audio(self) -> None:
        """提交当前音频缓冲区。"""
        await self.send({"type": "input_audio_buffer.commit"})

    async def create_response(self) -> None:
        """触发一轮模型响应。"""
        await self.send(
            {
                "type": "response.create",
                "response": {"modalities": ["audio", "text"]},
            }
        )

    async def cancel_response(self) -> None:
        """取消当前模型响应。"""
        await self.send({"type": "response.cancel"})

    async def update_instructions(self, instructions: str) -> None:
        """追加当前会话提示词。"""
        self.instructions = instructions
        await self.send(
            {
                "type": "session.update",
                "session": {"instructions": instructions},
            }
        )

    async def send_tool_result(self, call_id: str, result: Any) -> None:
        """写回 Function Calling 结果。"""
        await self.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                },
            }
        )

    async def events(self) -> AsyncGenerator[dict[str, Any], None]:
        """持续读取并解析上游事件。"""
        if self.websocket is None:
            raise RuntimeError("Qwen 实时连接尚未建立")
        while True:
            try:
                raw = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=self.timeout,
                )
            except TimeoutError:
                yield {"type": "error", "error": {"message": "上游语音模型响应超时"}}
                return
            except ConnectionClosed as exc:
                yield {
                    "type": "error",
                    "error": {"message": f"上游语音模型连接中断: {exc.code}"},
                }
                return
            if isinstance(raw, bytes):
                # Qwen 文档约定 JSON 事件；兼容供应商直接返回音频二进制帧。
                yield {"type": "response.audio.delta.binary", "audio": raw}
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                yield {"type": "error", "error": {"message": "上游事件不是合法 JSON"}}
                continue
            if isinstance(payload, dict):
                yield payload

    async def close(self) -> None:
        """关闭上游连接。"""
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                logger.exception("关闭 Qwen 实时连接失败")
