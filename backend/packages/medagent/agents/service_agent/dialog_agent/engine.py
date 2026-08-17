"""Dialog Agent 双引擎抽象与协议适配。"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import websockets
from openai import AsyncOpenAI
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class DialogEngine(ABC):
    """屏蔽语音和文本供应商差异的统一对话引擎接口。"""

    @abstractmethod
    async def create_session(
        self,
        system_prompt: str,
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """创建会话。"""

    @abstractmethod
    async def send_input(self, input_data: Any) -> None:
        """发送患者输入。"""

    @abstractmethod
    async def stream_response(self) -> AsyncGenerator[dict[str, Any], None]:
        """输出统一事件流。"""
        if False:
            yield {}

    @abstractmethod
    async def send_tool_result(self, call_id: str, result: Any) -> bool:
        """回传工具结果，并说明上层是否需要发起下一次响应读取。"""

    @abstractmethod
    async def update_session(
        self,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """动态更新会话。"""

    @abstractmethod
    async def close_session(self) -> None:
        """关闭会话。"""


class DoubaoVoiceEngine(DialogEngine):
    """基于 WebSocket JSON 事件协议的豆包实时语音适配器。"""

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-voice-v1",
        ws_url: str = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary",
        timeout: float = 30.0,
        *,
        connector: Callable[..., Awaitable[Any]] | None = None,
        reconnect_attempts: int = 1,
    ) -> None:
        if reconnect_attempts < 0:
            raise ValueError("reconnect_attempts 不能小于 0")
        self.api_key = api_key
        self.model = model
        self.ws_url = ws_url
        self.timeout = timeout
        self.connector = connector or websockets.connect
        self.reconnect_attempts = reconnect_attempts
        self.websocket: Any | None = None
        self.session_id: str | None = None
        self.conversation_id: str | None = None
        self.system_prompt: str | None = None
        self.tools: list[dict[str, Any]] = []
        self.voice = "zh-CN-YunxiNeural"
        self.audio_format = "pcm"

    @staticmethod
    def _is_open(websocket: Any | None) -> bool:
        if websocket is None:
            return False
        closed = getattr(websocket, "closed", None)
        if closed is not None:
            return not bool(closed)
        state = getattr(websocket, "state", None)
        if state is None:
            return True
        return getattr(state, "name", "") == "OPEN" or state == 1

    async def _connect(self) -> None:
        self.websocket = await self.connector(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            ping_interval=20,
            ping_timeout=10,
            open_timeout=self.timeout,
        )

    def _session_create_payload(self) -> dict[str, Any]:
        return {
            "type": "session.create",
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "model": self.model,
            "instructions": self.system_prompt,
            "voice": self.voice,
            "tools": self.tools,
            "audio_format": {
                "type": self.audio_format,
                "sample_rate": 16000,
                "channels": 1,
            },
        }

    async def _create_remote_session(self) -> None:
        if not self._is_open(self.websocket):
            raise RuntimeError("WebSocket 未连接")
        websocket = self.websocket
        assert websocket is not None
        await websocket.send(json.dumps(self._session_create_payload()))
        response = await asyncio.wait_for(
            websocket.recv(),
            timeout=self.timeout,
        )
        if isinstance(response, bytes):
            response = response.decode("utf-8")
        payload = json.loads(response)
        if not isinstance(payload, dict) or payload.get("type") != "session.created":
            raise RuntimeError(f"会话创建失败: {payload}")

    async def create_session(
        self,
        system_prompt: str,
        tools: list[dict[str, Any]],
        *,
        voice: str = "zh-CN-YunxiNeural",
        audio_format: str = "pcm",
        **_kwargs: Any,
    ) -> None:
        self.session_id = str(uuid.uuid4())
        self.conversation_id = str(uuid.uuid4())
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.voice = voice
        self.audio_format = audio_format
        try:
            await self._connect()
            await self._create_remote_session()
        except Exception:
            logger.exception("[DoubaoVoiceEngine] 创建会话失败")
            await self.close_session()
            raise

    async def _reconnect(self) -> None:
        await self._close_socket(send_close=False)
        await self._connect()
        await self._create_remote_session()

    async def send_input(self, input_data: Any) -> None:
        if not isinstance(input_data, bytes):
            raise TypeError("DoubaoVoiceEngine 仅接受 PCM bytes")
        payloads = [
            {
                "type": "input.audio.buffer.append",
                "audio": base64.b64encode(input_data).decode("utf-8"),
            },
            {"type": "input.audio.buffer.commit"},
        ]
        for attempt in range(self.reconnect_attempts + 1):
            if not self._is_open(self.websocket):
                if attempt >= self.reconnect_attempts:
                    raise RuntimeError("WebSocket 未连接或已关闭")
                await self._reconnect()
            try:
                websocket = self.websocket
                assert websocket is not None
                for payload in payloads:
                    await websocket.send(json.dumps(payload))
                return
            except ConnectionClosed:
                if attempt >= self.reconnect_attempts:
                    raise
                await self._reconnect()

    async def stream_response(self) -> AsyncGenerator[dict[str, Any], None]:
        reconnects = 0
        while True:
            if not self._is_open(self.websocket):
                yield {"type": "error", "message": "WebSocket 未连接"}
                return
            websocket = self.websocket
            assert websocket is not None
            try:
                raw_message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=self.timeout,
                )
            except TimeoutError:
                yield {"type": "error", "message": "响应超时"}
                return
            except ConnectionClosed:
                if reconnects >= self.reconnect_attempts:
                    yield {"type": "error", "message": "WebSocket 连接中断"}
                    return
                reconnects += 1
                try:
                    await self._reconnect()
                    continue
                except Exception:
                    logger.exception("[DoubaoVoiceEngine] 断线重连失败")
                    yield {"type": "error", "message": "WebSocket 重连失败"}
                    return

            if isinstance(raw_message, bytes):
                yield {"type": "audio", "data": raw_message}
                continue
            try:
                message = json.loads(raw_message)
            except (TypeError, json.JSONDecodeError):
                yield {"type": "error", "message": "WebSocket 消息不是合法 JSON"}
                return
            if not isinstance(message, dict):
                yield {"type": "error", "message": "WebSocket 消息格式错误"}
                return

            message_type = message.get("type")
            if message_type == "input.audio.transcription.completed":
                yield {
                    "type": "user_transcript",
                    "text": str(message.get("transcript", "")),
                }
            elif message_type == "response.text.delta":
                yield {"type": "text", "content": str(message.get("delta", ""))}
            elif message_type == "response.audio.delta":
                try:
                    audio = base64.b64decode(message.get("delta", ""), validate=True)
                except (TypeError, ValueError):
                    yield {"type": "error", "message": "音频数据不是合法 base64"}
                    return
                yield {"type": "audio", "data": audio}
            elif message_type == "response.function_call":
                arguments = message.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        yield {"type": "error", "message": "工具参数不是合法 JSON"}
                        return
                if not isinstance(arguments, dict):
                    yield {"type": "error", "message": "工具参数格式错误"}
                    return
                yield {
                    "type": "tool_call",
                    "call_id": message.get("call_id"),
                    "name": message.get("name"),
                    "arguments": arguments,
                }
            elif message_type == "response.done":
                yield {"type": "response_done"}
                return
            elif message_type == "error":
                yield {
                    "type": "error",
                    "message": str(message.get("message", "未知错误")),
                }
                return

    async def send_tool_result(self, call_id: str, result: Any) -> bool:
        if not call_id:
            raise ValueError("call_id 不能为空")
        if not self._is_open(self.websocket):
            raise RuntimeError("WebSocket 未连接")
        websocket = self.websocket
        assert websocket is not None
        await websocket.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    },
                }
            )
        )
        return False

    async def update_session(
        self,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self._is_open(self.websocket):
            raise RuntimeError("WebSocket 未连接")
        websocket = self.websocket
        assert websocket is not None
        payload: dict[str, Any] = {
            "type": "session.update",
            "session_id": self.session_id,
        }
        if instructions:
            payload["instructions"] = instructions
        if tools is not None:
            payload["tools"] = tools
            self.tools = list(tools)
        await websocket.send(json.dumps(payload))

    async def _close_socket(self, *, send_close: bool) -> None:
        websocket = self.websocket
        self.websocket = None
        if not self._is_open(websocket):
            return
        assert websocket is not None
        try:
            if send_close:
                await websocket.send(
                    json.dumps(
                        {"type": "session.close", "session_id": self.session_id}
                    )
                )
            await websocket.close()
        except Exception:
            logger.exception("[DoubaoVoiceEngine] 关闭 WebSocket 失败")

    async def close_session(self) -> None:
        await self._close_socket(send_close=True)


class TextChatEngine(DialogEngine):
    """基于 OpenAI 兼容 Chat Completions 的文本降级引擎。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: str,
        timeout: float = 30.0,
        *,
        client: Any | None = None,
    ) -> None:
        self.client: Any = client or AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout,
        )
        self.model = model
        self.timeout = timeout
        self.system_prompt: str | None = None
        self.tools: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []

    async def create_session(
        self,
        system_prompt: str,
        tools: list[dict[str, Any]],
        **_kwargs: Any,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.messages = [{"role": "system", "content": system_prompt}]

    async def send_input(self, input_data: Any) -> None:
        if not isinstance(input_data, str):
            raise TypeError("TextChatEngine 仅接受文本输入")
        self.messages.append({"role": "user", "content": input_data})

    async def stream_response(self) -> AsyncGenerator[dict[str, Any], None]:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools or None,
                stream=True,
                temperature=0.7,
            )
            full_text = ""
            pending_calls: dict[int, dict[str, Any]] = {}
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_text += delta.content
                    yield {"type": "text", "content": delta.content}
                for tool_call in delta.tool_calls or []:
                    index = int(tool_call.index or 0)
                    pending = pending_calls.setdefault(
                        index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if tool_call.id:
                        pending["id"] = tool_call.id
                    function = tool_call.function
                    if function:
                        if function.name:
                            pending["name"] += function.name
                        if function.arguments:
                            pending["arguments"] += function.arguments

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": full_text or None,
            }
            if pending_calls:
                assistant_calls: list[dict[str, Any]] = []
                for index in sorted(pending_calls):
                    pending = pending_calls[index]
                    try:
                        arguments = json.loads(pending["arguments"] or "{}")
                    except json.JSONDecodeError:
                        yield {"type": "error", "message": "工具参数不是合法 JSON"}
                        return
                    if not pending["id"] or not pending["name"]:
                        yield {"type": "error", "message": "工具调用信息不完整"}
                        return
                    assistant_calls.append(
                        {
                            "id": pending["id"],
                            "type": "function",
                            "function": {
                                "name": pending["name"],
                                "arguments": pending["arguments"] or "{}",
                            },
                        }
                    )
                    yield {
                        "type": "tool_call",
                        "call_id": pending["id"],
                        "name": pending["name"],
                        "arguments": arguments,
                    }
                assistant_message["tool_calls"] = assistant_calls
            if full_text or pending_calls:
                self.messages.append(assistant_message)
            yield {"type": "response_done"}
        except Exception:
            logger.exception("[TextChatEngine] 流式响应失败")
            yield {"type": "error", "message": "文本模型调用失败"}

    async def send_tool_result(self, call_id: str, result: Any) -> bool:
        if not call_id:
            raise ValueError("call_id 不能为空")
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
        return True

    async def update_session(
        self,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        if instructions:
            self.messages.append({"role": "system", "content": instructions})
        if tools is not None:
            self.tools = list(tools)

    async def close_session(self) -> None:
        self.messages.clear()
        close = getattr(self.client, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result
