"""Dialog Engine 抽象层与实现
作用：DialogEngine 抽象基类 + DoubaoVoiceEngine（豆包全双工）+ TextChatEngine（文本降级）。
"""
import asyncio
import base64
import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

import websockets
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


# ==================== DialogEngine 抽象基类 ====================


class DialogEngine(ABC):
    """对话引擎抽象基类
    作用：定义对话引擎的统一接口，屏蔽底层协议差异。
    """

    @abstractmethod
    async def create_session(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> None:
        """创建对话会话
        Args:
            - system_prompt: 系统提示词
            - tools: 工具列表（OpenAI Function Call 格式）
            - **kwargs: 引擎特定参数（voice、audio_format 等）
        """
        pass

    @abstractmethod
    async def send_input(self, input_data: Any) -> None:
        """发送用户输入（音频或文本）
        Args:
            - input_data: 输入数据（音频 bytes 或文本 str）
        """
        pass

    @abstractmethod
    async def stream_response(self) -> AsyncGenerator[Dict[str, Any], None]:
        """流式接收 AI 响应
        作用：归一化输出事件：user_transcript|text|audio|tool_call|response_done|error
        Yield:
            - 事件字典：{"type": "text", "content": "...", ...}
        """
        pass

    @abstractmethod
    async def send_tool_result(self, call_id: str, result: Any) -> None:
        """回传工具调用结果
        Args:
            - call_id: 工具调用 ID
            - result: 工具执行结果
        """
        pass

    @abstractmethod
    async def update_session(
        self,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """动态更新会话（约束注入）
        Args:
            - instructions: 追加指令（约束提示）
            - tools: 更新工具列表
        """
        pass

    @abstractmethod
    async def close_session(self) -> None:
        """关闭会话并清理资源"""
        pass


# ==================== DoubaoVoiceEngine 实现 ====================


class DoubaoVoiceEngine(DialogEngine):
    """豆包语音全双工引擎
    作用：基于 WebSocket 实现豆包实时语音全双工协议。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-voice-v1",
        ws_url: str = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary",
        timeout: float = 30.0,
    ):
        """初始化豆包语音引擎
        Args:
            - api_key: 豆包 API Key
            - model: 模型名称
            - ws_url: WebSocket 地址
            - timeout: 响应超时（秒）
        """
        self.api_key = api_key
        self.model = model
        self.ws_url = ws_url
        self.timeout = timeout

        self.session_id: Optional[str] = None
        self.conversation_id: Optional[str] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.system_prompt: Optional[str] = None
        self.tools: List[Dict[str, Any]] = []

        logger.info(f"[DoubaoVoiceEngine] 初始化: model={model}, ws_url={ws_url}")

    async def create_session(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        voice: str = "zh-CN-YunxiNeural",
        audio_format: str = "pcm",
        **kwargs,
    ) -> None:
        """创建豆包会话
        Args:
            - system_prompt: 系统提示词
            - tools: 工具列表
            - voice: 语音合成声音
            - audio_format: 音频格式（pcm/opus）
        """
        try:
            # 1. 建立 WebSocket 连接
            headers = {"Authorization": f"Bearer {self.api_key}"}
            self.websocket = await websockets.connect(
                self.ws_url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10,
            )
            logger.info("[DoubaoVoiceEngine] WebSocket 连接建立成功")

            # 2. 发送 session.create 消息
            self.session_id = str(uuid.uuid4())
            self.conversation_id = str(uuid.uuid4())
            self.system_prompt = system_prompt
            self.tools = tools

            create_msg = {
                "type": "session.create",
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "model": self.model,
                "instructions": system_prompt,
                "voice": voice,
                "tools": tools if tools else [],
                "audio_format": {"type": audio_format, "sample_rate": 16000, "channels": 1},
            }
            await self.websocket.send(json.dumps(create_msg))
            logger.info(f"[DoubaoVoiceEngine] 会话创建: session_id={self.session_id}")

            # 3. 等待 session.created 确认（带超时）
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=self.timeout,
            )
            resp_data = json.loads(response)
            if resp_data.get("type") != "session.created":
                raise RuntimeError(f"会话创建失败: {resp_data}")

            logger.info("[DoubaoVoiceEngine] 会话创建确认成功")

        except Exception as e:
            logger.error(f"[DoubaoVoiceEngine] 创建会话失败: {e}", exc_info=True)
            await self.close_session()
            raise

    async def send_input(self, input_data: Any) -> None:
        """发送音频输入
        Args:
            - input_data: 音频 bytes（PCM 16kHz/16bit mono）
        """
        if not self.websocket or self.websocket.closed:
            raise RuntimeError("WebSocket 未连接或已关闭")

        try:
            # 1. 发送 input.audio.buffer.append（音频数据 base64）
            audio_base64 = base64.b64encode(input_data).decode("utf-8")
            append_msg = {
                "type": "input.audio.buffer.append",
                "audio": audio_base64,
            }
            await self.websocket.send(json.dumps(append_msg))

            # 2. 发送 input.audio.buffer.commit（提交音频）
            commit_msg = {"type": "input.audio.buffer.commit"}
            await self.websocket.send(json.dumps(commit_msg))

            logger.debug(f"[DoubaoVoiceEngine] 音频输入已提交，大小={len(input_data)} bytes")

        except Exception as e:
            logger.error(f"[DoubaoVoiceEngine] 发送音频失败: {e}", exc_info=True)
            raise

    async def stream_response(self) -> AsyncGenerator[Dict[str, Any], None]:
        """流式接收 AI 响应
        Yield:
            - {"type": "user_transcript", "text": "..."} - 用户语音识别结果
            - {"type": "text", "content": "..."} - AI 文本增量
            - {"type": "audio", "data": bytes} - AI 语音增量
            - {"type": "tool_call", "call_id": "...", "name": "...", "arguments": {...}} - 工具调用
            - {"type": "response_done"} - 响应完成
            - {"type": "error", "message": "..."} - 错误
        """
        if not self.websocket or self.websocket.closed:
            yield {"type": "error", "message": "WebSocket 未连接"}
            return

        try:
            while True:
                # 接收消息（带超时）
                try:
                    raw_msg = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=self.timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning("[DoubaoVoiceEngine] 响应超时")
                    yield {"type": "error", "message": "响应超时"}
                    break

                # 解析消息
                try:
                    msg = json.loads(raw_msg) if isinstance(raw_msg, str) else raw_msg
                except json.JSONDecodeError:
                    # 二进制音频数据
                    yield {"type": "audio", "data": raw_msg}
                    continue

                msg_type = msg.get("type")

                # 1. 用户语音识别完成
                if msg_type == "input.audio.transcription.completed":
                    yield {
                        "type": "user_transcript",
                        "text": msg.get("transcript", ""),
                    }

                # 2. AI 文本增量
                elif msg_type == "response.text.delta":
                    yield {
                        "type": "text",
                        "content": msg.get("delta", ""),
                    }

                # 3. AI 语音增量
                elif msg_type == "response.audio.delta":
                    audio_b64 = msg.get("delta", "")
                    audio_bytes = base64.b64decode(audio_b64)
                    yield {
                        "type": "audio",
                        "data": audio_bytes,
                    }

                # 4. 工具调用
                elif msg_type == "response.function_call":
                    yield {
                        "type": "tool_call",
                        "call_id": msg.get("call_id"),
                        "name": msg.get("name"),
                        "arguments": json.loads(msg.get("arguments", "{}")),
                    }

                # 5. 响应完成
                elif msg_type == "response.done":
                    yield {"type": "response_done"}
                    break

                # 6. 错误
                elif msg_type == "error":
                    yield {
                        "type": "error",
                        "message": msg.get("message", "未知错误"),
                    }
                    break

        except Exception as e:
            logger.error(f"[DoubaoVoiceEngine] 流式响应异常: {e}", exc_info=True)
            yield {"type": "error", "message": str(e)}

    async def send_tool_result(self, call_id: str, result: Any) -> None:
        """回传工具调用结果
        Args:
            - call_id: 工具调用 ID
            - result: 工具执行结果
        """
        if not self.websocket or self.websocket.closed:
            raise RuntimeError("WebSocket 未连接")

        try:
            # 发送 conversation.item.create 消息
            result_msg = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                },
            }
            await self.websocket.send(json.dumps(result_msg))
            logger.debug(f"[DoubaoVoiceEngine] 工具结果已回传: call_id={call_id}")

        except Exception as e:
            logger.error(f"[DoubaoVoiceEngine] 回传工具结果失败: {e}", exc_info=True)
            raise

    async def update_session(
        self,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """动态更新会话
        Args:
            - instructions: 追加指令（约束提示）
            - tools: 更新工具列表
        """
        if not self.websocket or self.websocket.closed:
            raise RuntimeError("WebSocket 未连接")

        try:
            # 发送 session.update 消息
            update_msg = {
                "type": "session.update",
                "session_id": self.session_id,
            }
            if instructions:
                update_msg["instructions"] = instructions
            if tools:
                update_msg["tools"] = tools

            await self.websocket.send(json.dumps(update_msg))
            logger.info("[DoubaoVoiceEngine] 会话已更新（约束注入）")

        except Exception as e:
            logger.error(f"[DoubaoVoiceEngine] 更新会话失败: {e}", exc_info=True)
            raise

    async def close_session(self) -> None:
        """关闭会话"""
        try:
            if self.websocket and not self.websocket.closed:
                # 发送 session.close 消息
                close_msg = {"type": "session.close", "session_id": self.session_id}
                await self.websocket.send(json.dumps(close_msg))
                await self.websocket.close()
                logger.info("[DoubaoVoiceEngine] 会话已关闭")

        except Exception as e:
            logger.error(f"[DoubaoVoiceEngine] 关闭会话失败: {e}", exc_info=True)
        finally:
            self.websocket = None


# ==================== TextChatEngine 降级实现 ====================


class TextChatEngine(DialogEngine):
    """文本对话引擎（降级方案）
    作用：基于 AsyncOpenAI 实现文本对话，用于无豆包 Key 环境验证编排逻辑。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: str,
        timeout: float = 30.0,
    ):
        """初始化文本对话引擎
        Args:
            - api_key: OpenAI 兼容 API Key
            - model: 模型名称
            - api_base: API Base URL
            - timeout: 超时时间
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=timeout,
        )
        self.model = model
        self.timeout = timeout

        self.system_prompt: Optional[str] = None
        self.tools: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, str]] = []

        logger.info(f"[TextChatEngine] 初始化: model={model}, api_base={api_base}")

    async def create_session(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> None:
        """创建文本会话
        Args:
            - system_prompt: 系统提示词
            - tools: 工具列表
        """
        self.system_prompt = system_prompt
        self.tools = tools
        self.messages = [{"role": "system", "content": system_prompt}]
        logger.info("[TextChatEngine] 文本会话已创建")

    async def send_input(self, input_data: Any) -> None:
        """发送文本输入
        Args:
            - input_data: 文本字符串
        """
        if not isinstance(input_data, str):
            raise ValueError("TextChatEngine 仅接受文本输入")

        self.messages.append({"role": "user", "content": input_data})
        logger.debug(f"[TextChatEngine] 文本输入已接收: {input_data[:50]}...")

    async def stream_response(self) -> AsyncGenerator[Dict[str, Any], None]:
        """流式接收 AI 响应
        Yield:
            - {"type": "text", "content": "..."} - AI 文本增量
            - {"type": "tool_call", ...} - 工具调用
            - {"type": "response_done"} - 响应完成
        """
        try:
            # 调用 OpenAI Chat Completion
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tools if self.tools else None,
                stream=True,
                temperature=0.7,
            )

            full_text = ""
            tool_calls = []

            async for chunk in response:
                delta = chunk.choices[0].delta

                # 1. 文本增量
                if delta.content:
                    full_text += delta.content
                    yield {"type": "text", "content": delta.content}

                # 2. 工具调用
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        tool_calls.append(tool_call)
                        yield {
                            "type": "tool_call",
                            "call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": json.loads(tool_call.function.arguments),
                        }

            # 3. 保存 assistant 消息到历史
            if full_text:
                self.messages.append({"role": "assistant", "content": full_text})

            yield {"type": "response_done"}

        except Exception as e:
            logger.error(f"[TextChatEngine] 流式响应异常: {e}", exc_info=True)
            yield {"type": "error", "message": str(e)}

    async def send_tool_result(self, call_id: str, result: Any) -> None:
        """回传工具调用结果
        Args:
            - call_id: 工具调用 ID
            - result: 工具执行结果
        """
        # 添加 tool 消息到历史
        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result, ensure_ascii=False),
        })
        logger.debug(f"[TextChatEngine] 工具结果已记录: call_id={call_id}")

    async def update_session(
        self,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """动态更新会话
        Args:
            - instructions: 追加指令（约束提示）
            - tools: 更新工具列表
        """
        if instructions:
            # 在 messages 中插入 system 消息（作为约束）
            self.messages.append({"role": "system", "content": instructions})
            logger.info("[TextChatEngine] 约束已注入")

        if tools:
            self.tools = tools
            logger.info("[TextChatEngine] 工具列表已更新")

    async def close_session(self) -> None:
        """关闭会话"""
        self.messages.clear()
        logger.info("[TextChatEngine] 文本会话已关闭")
