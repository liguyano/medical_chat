"""Dialog Agent 核心编排。

通过依赖注入整合引擎、中间件、状态和历史，不依赖具体应用层实现。
"""

from __future__ import annotations

import logging
from typing import Any

from ...middlewares.base import DialogMiddleware, MiddlewareChain
from ..schedule_agent import QuestionTask
from .engine import DialogEngine
from .models import (
    DialogHistoryStore,
    DialogStateStore,
    DialogTextDeltaSink,
    DialogToolExecutor,
)
from .prompt import build_constraint_update_prompt, build_system_prompt
from .tools import DIALOG_TOOLS, execute_tool

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "抱歉，系统暂时无法处理您的输入，请稍后再试。"
MAX_TOOL_RESPONSE_ROUNDS = 4


class DialogAgent:
    """驱动统一对话引擎和可组合中间件的 SDK 智能体。"""

    def __init__(
        self,
        session_id: str,
        patient_info: dict[str, Any],
        task_list: list[QuestionTask],
        engine: DialogEngine,
        *,
        middlewares: list[DialogMiddleware] | None = None,
        state_store: DialogStateStore | None = None,
        history_store: DialogHistoryStore | None = None,
        tool_executor: DialogToolExecutor = execute_tool,
        text_delta_sink: DialogTextDeltaSink | None = None,
    ) -> None:
        self.session_id = session_id
        self.patient_info = patient_info
        self.task_list = task_list
        self.engine = engine
        self.middleware = MiddlewareChain(middlewares or [])
        self.state_store = state_store
        self.history_store = history_store
        self.tool_executor = tool_executor
        self.text_delta_sink = text_delta_sink
        self.turn_counter = 0
        self.last_turn_context: dict[str, Any] = {}

    async def initialize(self) -> None:
        """创建引擎会话并保存初始状态。"""
        system_prompt = build_system_prompt(
            patient_info=self.patient_info,
            task_list=self.task_list,
        )
        await self.engine.create_session(
            system_prompt=system_prompt,
            tools=DIALOG_TOOLS,
        )
        if self.state_store is not None:
            saved = await self.state_store.save_agent_state(
                self.session_id,
                {
                    "session_id": self.session_id,
                    "patient_info": self.patient_info,
                    "turn_counter": self.turn_counter,
                    "engine_type": self.engine.__class__.__name__,
                },
            )
            if not saved:
                await self.engine.close_session()
                raise RuntimeError("Dialog Agent 初始状态保存失败")

    async def handle_patient_input(
        self,
        audio_or_text: Any,
        session_no: str | None = None,
        context_metadata: dict[str, Any] | None = None,
    ) -> str:
        """处理一轮患者输入并返回完整 AI 文本。"""
        self.turn_counter += 1
        text_input = audio_or_text if isinstance(audio_or_text, str) else ""
        context: dict[str, Any] = {
            "session_id": self.session_id,
            "turn_number": self.turn_counter,
            "patient_input": text_input,
            "constraints": [],
            "tool_calls": [],
        }
        if context_metadata:
            context.update(context_metadata)
        applied_constraints = 0

        try:
            await self.middleware.execute_before(context)
            applied_constraints = await self._apply_new_constraints(
                context,
                applied_constraints,
            )

            if text_input and session_no:
                await self._save_history(
                    session_no,
                    role_type="患者",
                    message_type="文本",
                    content_text=text_input,
                )

            await self.engine.send_input(audio_or_text)
            full_response_text = ""
            response_failed = False
            for _ in range(MAX_TOOL_RESPONSE_ROUNDS):
                followup_required = False
                async for event in self.engine.stream_response():
                    event_type = event.get("type")
                    if event_type == "user_transcript":
                        transcript = str(event.get("text", ""))
                        context["patient_input"] = transcript
                        if transcript and not text_input:
                            await self.middleware.execute_before(context)
                            applied_constraints = await self._apply_new_constraints(
                                context,
                                applied_constraints,
                            )
                            if session_no:
                                await self._save_history(
                                    session_no,
                                    role_type="患者",
                                    message_type="语音",
                                    content_text=transcript,
                                    asr_text=transcript,
                                )
                    elif event_type == "text":
                        text_chunk = str(event.get("content", ""))
                        full_response_text += text_chunk
                        if self.text_delta_sink and text_chunk:
                            await self.text_delta_sink(
                                text_chunk,
                                {
                                    **context,
                                    "full_response_text": full_response_text,
                                },
                            )
                    elif event_type == "audio":
                        context.setdefault("audio_chunks", []).append(event.get("data"))
                    elif event_type == "tool_call":
                        followup_required = (
                            await self._handle_tool_call(event, context) or followup_required
                        )
                    elif event_type == "response_done":
                        break
                    elif event_type == "error":
                        logger.error(
                            "[DialogAgent] 引擎返回错误: %s",
                            event.get("message", "未知错误"),
                        )
                        full_response_text = GENERIC_ERROR_MESSAGE
                        response_failed = True
                        break
                if response_failed or not followup_required:
                    break
            else:
                logger.error(
                    "[DialogAgent] 工具调用超过最大轮次: session=%s",
                    self.session_id,
                )
                full_response_text = GENERIC_ERROR_MESSAGE

            if session_no and full_response_text:
                await self._save_history(
                    session_no,
                    role_type="AI",
                    message_type="语音" if not text_input else "文本",
                    content_text=full_response_text,
                    tts_text=full_response_text if not text_input else None,
                )

            await self.middleware.execute_after(context, full_response_text)
            self.last_turn_context = context
            await self._update_state()
            return full_response_text
        except Exception:
            logger.exception(
                "[DialogAgent] 处理患者输入失败: session=%s turn=%s",
                self.session_id,
                self.turn_counter,
            )
            await self.middleware.execute_after(context, GENERIC_ERROR_MESSAGE)
            self.last_turn_context = context
            return GENERIC_ERROR_MESSAGE

    async def _apply_new_constraints(
        self,
        context: dict[str, Any],
        applied_count: int,
    ) -> int:
        constraints = list(context.get("constraints") or [])
        new_constraints = constraints[applied_count:]
        if new_constraints:
            await self.engine.update_session(
                instructions=build_constraint_update_prompt(new_constraints)
            )
        return len(constraints)

    async def _handle_tool_call(
        self,
        event: dict[str, Any],
        context: dict[str, Any],
    ) -> bool:
        call_id = str(event.get("call_id") or "")
        tool_name = str(event.get("name") or "")
        arguments = event.get("arguments")
        if not call_id or not tool_name or not isinstance(arguments, dict):
            logger.warning("[DialogAgent] 忽略损坏的工具调用事件: %r", event)
            return False

        try:
            result = await self.tool_executor(tool_name, arguments)
        except Exception:
            logger.exception("[DialogAgent] 工具执行失败: %s", tool_name)
            result = {"success": False, "message": "工具执行失败"}

        context["tool_calls"].append(
            {
                "call_id": call_id,
                "name": tool_name,
                "arguments": arguments,
                "result": result,
            }
        )
        return bool(await self.engine.send_tool_result(call_id, result))

    async def _save_history(
        self,
        session_no: str,
        *,
        role_type: str,
        message_type: str,
        content_text: str,
        asr_text: str | None = None,
        tts_text: str | None = None,
    ) -> None:
        if self.history_store is None:
            return
        await self.history_store.save_message(
            session_no,
            turn_no=self.turn_counter,
            role_type=role_type,
            message_type=message_type,
            content_text=content_text,
            asr_text=asr_text,
            tts_text=tts_text,
        )

    async def _update_state(self) -> None:
        if self.state_store is None:
            return
        saved = await self.state_store.save_agent_state(
            self.session_id,
            {
                "session_id": self.session_id,
                "turn_counter": self.turn_counter,
                "patient_info": self.patient_info,
            },
        )
        if not saved:
            logger.error("[DialogAgent] 状态更新失败: %s", self.session_id)

    async def close(self) -> None:
        """关闭底层引擎并释放资源。"""
        await self.engine.close_session()
