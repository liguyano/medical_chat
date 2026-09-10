"""患者端实时语音网关。

作用：托管单个会话的 Qwen 实时语音上游连接，将音频低延迟转发给患者，
同时把转写、文本、工具和音频索引写入现有 Redis Stream，供患者端和医护端
通过 SSE 续读。该模块不调用文本 Dialog Agent，避免与纯文本链路重复生成。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from medagent.agents.service_agent.dialog_agent.prompt import build_system_prompt
from medagent.agents.service_agent.dialog_agent.tools import DIALOG_TOOLS
from medagent.agents.service_agent.schedule_agent import QuestionTask
from sqlalchemy import func, select

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.managers.dialog_history_manager import DialogHistoryManager
from app.managers.keyword_matcher import get_keyword_matcher
from app.models import base as model_base
from app.models.interaction import InteractionMessage, InteractionSession
from app.schemas.events import (
    AgentErrorEvent,
    AssistantMessageStartedEvent,
    DialogAudioEvent,
    DialogMessageEvent,
    DialogTextEvent,
    PatientAnswerEvent,
    PatientAudioEvent,
    ToolCallEvent,
)
from app.services.agent_dispatch_service import dispatch_voice_answer_workers
from app.services.dialog_audio_store import DialogAudioStore
from app.services.dialog_tool_executor import execute_tool
from app.services.manual_review_service import (
    ensure_planned_manual_review_notification,
)
from app.services.qwen_realtime_client import QwenRealtimeClient
from app.services.tool_interaction_service import publish_tool_result
from app.services.voice_turn_guard import VoiceTurnGuard
from app.utils.redis_client import RedisClient, get_redis
from app.workers.event_publisher import DialogEventPublisher
from app.workers.schedule_task_store import ScheduleTaskStore

logger = logging.getLogger(__name__)


VOICE_GRACE_SECONDS = 180
TRANSCRIPT_DRAFT_TTL_SECONDS = 900
TRANSCRIPT_PENDING_KEY_PREFIX = "voice_transcript_pending:"
MAX_AUDIO_BUFFER_BYTES = 12 * 1024 * 1024
INPUT_PRE_ROLL_BYTES = 32_000
VOICE_CLOSE_RECOVERY_POLL_SECONDS = 0.25
VOICE_CLOSE_RECOVERY_TIMEOUT_SECONDS = 20.0


@dataclass
class VoiceGeneration:
    """一轮模型响应的运行态。"""

    generation_id: str
    message_id: str
    turn_no: int
    response_id: str | None = None
    text: str = ""
    audio: bytearray = field(default_factory=bytearray)
    all_audio: bytearray = field(default_factory=bytearray)
    audio_segment_no: int = 0
    audio_format: str = "wav"
    sample_rate: int = 24000
    text_source: str | None = None
    tool_call_only: bool = False
    started_event_id: str | None = None
    completed: bool = False
    is_recovery: bool = False
    is_manual_review_completion: bool = False


@dataclass
class VoiceSession:
    """单个业务会话的实时语音运行态。"""

    session_no: str
    task_id: int
    patient_id: int
    patient_info: dict[str, Any]
    scale_codes: list[str]
    instructions: str
    client: QwenRealtimeClient
    redis: RedisClient
    audio_store: DialogAudioStore
    publisher: DialogEventPublisher
    task_list: list[QuestionTask] = field(default_factory=list)
    turn_detection: str = "server_vad"
    connected_clients: set[WebSocket] = field(default_factory=set)
    input_audio: bytearray = field(default_factory=bytearray)
    input_pre_roll: bytearray = field(default_factory=bytearray)
    input_turn_no: int = 0
    input_message_id: str | None = None
    input_audio_url: str | None = None
    speech_active: bool = False
    input_committed: bool = False
    transcript_received: bool = False
    response_requested: bool = False
    responding: bool = False
    audio_suppressed: bool = False
    current_response_id: str | None = None
    current_generation: VoiceGeneration | None = None
    generations: dict[str, VoiceGeneration] = field(default_factory=dict)
    active_response_ids: set[str] = field(default_factory=set)
    suppressed_response_ids: set[str] = field(default_factory=set)
    pending_tool_responses: int = 0
    response_create_pending: bool = False
    response_create_attempts: int = 0
    response_cancel_requested: bool = False
    handled_tool_call_ids: set[str] = field(default_factory=set)
    receive_task: Any | None = None
    close_task: Any | None = None
    recovery_task: Any | None = None
    manual_review_completion_task: Any | None = None
    recovery_mode_active: bool = False
    recovery_current_question_id: int | None = None
    recovery_source_message_no: str | None = None
    recovery_answer_response_pending: bool = False
    next_response_is_recovery: bool = False
    next_response_is_manual_review_completion: bool = False
    recovery_instruction_active: bool = False
    closed: bool = False
    # 默认识别完成即提交；仅在显式启用时保留转写确认草稿协议，兼容历史客户端/测试。
    require_transcript_confirmation: bool = False
    pending_transcript_id: str | None = None
    pending_transcript_text: str | None = None
    pending_transcript_turn_no: int = 0
    pending_transcript_message_id: str | None = None
    pending_transcript_audio_url: str | None = None
    confirmed_transcript_id: str | None = None
    discarded_transcript_ids: set[str] = field(default_factory=set)


class VoiceGateway:
    """进程内 Voice Gateway 注册表。

    业务事件和消息历史是持久化事实；本注册表只保留上游 WebSocket 和连接
    订阅者，进程重启后可以依据历史重新建立会话。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_no_active_response_error(error: dict[str, Any]) -> bool:
        """识别 Qwen 在取消/重复触发响应竞态下返回的可恢复错误。"""
        message = str(error.get("message") or "").lower()
        code = str(error.get("code") or "").lower()
        return (
            "conversation has no active response" in message
            or code in {"no_active_response", "conversation_no_active_response"}
        )

    async def _maybe_create_response(self, session: VoiceSession) -> None:
        """在工具结果写回后，等待当前响应结束再幂等触发下一轮响应。"""
        if (
            not session.response_create_pending
            or session.closed
            or session.speech_active
            or session.responding
            or session.active_response_ids
            or session.response_requested
        ):
            return
        if session.response_create_attempts >= 3:
            logger.error(
                "语音工具响应连续触发失败，保留待处理状态等待下一轮: session=%s",
                session.session_no,
            )
            return
        session.response_create_pending = False
        session.response_create_attempts += 1
        session.response_requested = True
        try:
            await session.client.create_response()
        except Exception:
            session.response_requested = False
            session.response_create_pending = True
            logger.exception(
                "语音工具结果触发 response.create 失败: session=%s",
                session.session_no,
            )

    async def get_or_create(
        self,
        *,
        session_no: str,
        task_id: int,
        patient_id: int,
        patient_info: dict[str, Any],
        scale_codes: list[str],
    ) -> VoiceSession:
        async with self._lock:
            existing = self._sessions.get(session_no)
            if existing is not None and not existing.closed:
                return existing
            from medagent.configs.model_config import ModelType

            voice_config = get_app_config().get_agent_model_config(
                "dialog_agent", ModelType.VOICE
            )
            if voice_config is None or not voice_config.websocket_url:
                raise AppError(
                    ErrorCode.ERR_DIALOG_001,
                    "未配置 Qwen 实时语音模型，请先配置 dialog_agent.voice",
                    http_status=503,
                )
            provider = str((voice_config.model_extra or {}).get("provider") or "")
            if provider and provider not in {"qwen_audio_realtime", "qwen_omni_realtime"}:
                raise AppError(
                    ErrorCode.ERR_DIALOG_001,
                    "当前语音模型不是 Qwen Realtime 协议，无法建立语音会话",
                    http_status=503,
                )
            redis = get_redis()
            plan = ScheduleTaskStore(redis).get_plan(session_no)
            task_list = plan.tasks if plan is not None else []
            base_instructions = build_system_prompt(
                patient_info=patient_info,
                task_list=task_list,
            )

            initial_recovery_mode = False
            initial_recovery_question_id: int | None = None
            connect_instructions = base_instructions
            try:
                initial_decision = await asyncio.to_thread(
                    VoiceTurnGuard.build_recovery_decision,
                    session_no,
                    task_list,
                )
            except Exception:
                logger.exception(
                    "建立语音会话前读取结构化进度失败，拒绝根据未知状态裁剪题表: "
                    "session=%s",
                    session_no,
                )
                raise

            if initial_decision.progress.completed:
                connect_instructions = self._build_completed_wait_instructions()
                logger.info(
                    "重新进入已完成语音评估，禁止继续提问: session=%s progress=%s/%s",
                    session_no,
                    initial_decision.progress.current,
                    initial_decision.progress.total,
                )
            elif initial_decision.progress.current > 0:
                initial_recovery_mode = True
                if initial_decision.next_question is not None:
                    initial_recovery_question_id = (
                        initial_decision.next_question.question_id
                    )
                    connect_instructions = self._build_recovery_question_instructions(
                        patient_info,
                        initial_decision.next_question,
                        mode_label="会话恢复模式",
                        transition_rule=(
                            "这是重新进入已有评估会话。不要重新开场或回顾已完成问题，"
                            "直接自然继续确认下面这一项。"
                        ),
                    )
                    logger.info(
                        "重新进入未完成语音评估，仅暴露首个 remaining 问题: "
                        "session=%s progress=%s/%s question_id=%s remaining=%s",
                        session_no,
                        initial_decision.progress.current,
                        initial_decision.progress.total,
                        initial_recovery_question_id,
                        list(initial_decision.progress.remaining_question_ids),
                    )
                else:
                    connect_instructions = self._build_recovery_mapping_error_instructions()
                    logger.error(
                        "重新进入语音评估时 remaining 无法映射到 Task-todo，"
                        "禁止回退完整题表: session=%s remaining=%s",
                        session_no,
                        list(initial_decision.progress.remaining_question_ids),
                    )

            client = QwenRealtimeClient(
                api_key=voice_config.resolved_api_key(),
                model=voice_config.model,
                websocket_url=voice_config.websocket_url,
                voice=voice_config.voice or "longanqian",
                timeout=voice_config.timeout,
            )
            voice_extra = voice_config.model_extra or {}
            turn_detection = str(voice_extra.get("turn_detection") or "server_vad")
            await client.connect(
                instructions=connect_instructions,
                tools=DIALOG_TOOLS,
                turn_detection=turn_detection,
                vad_threshold=float(voice_extra.get("vad_threshold", 0.1)),
                silence_duration_ms=int(
                    voice_extra.get("silence_duration_ms", 900)
                ),
                max_history_turns=int(voice_extra.get("max_history_turns", 50)),
            )
            gateway_session = VoiceSession(
                session_no=session_no,
                task_id=task_id,
                patient_id=patient_id,
                patient_info=patient_info,
                scale_codes=scale_codes,
                instructions=base_instructions,
                client=client,
                redis=redis,
                audio_store=DialogAudioStore(),
                publisher=DialogEventPublisher(session_no),
                task_list=task_list,
                turn_detection=turn_detection,
                recovery_mode_active=initial_recovery_mode,
                recovery_current_question_id=initial_recovery_question_id,
                recovery_instruction_active=initial_recovery_mode,
                require_transcript_confirmation=False,
            )
            self._sessions[session_no] = gateway_session
            gateway_session.receive_task = asyncio.create_task(
                self._consume_upstream(gateway_session)
            )
            if (
                initial_decision.progress.completed
                and int(patient_info.get("manual_review_count") or 0) > 0
            ):
                gateway_session.manual_review_completion_task = asyncio.create_task(
                    self._start_manual_review_completion_response(gateway_session)
                )
            return gateway_session

    async def attach(self, session: VoiceSession, websocket: WebSocket) -> None:
        """绑定患者端 WebSocket。"""
        session.connected_clients.add(websocket)
        if session.close_task is not None:
            session.close_task.cancel()
            session.close_task = None
        await self._send_json(websocket, {"type": "ready"})
        await self._send_json(
            websocket,
            {
                "type": "mode",
                "turn_detection": session.turn_detection,
            },
        )
        await self._send_json(websocket, {"type": "state", "state": "listening"})
        self._restore_pending_transcript(session)
        if session.pending_transcript_id and session.pending_transcript_text:
            await self._send_json(
                websocket,
                {
                    "type": "transcript_ready",
                    "transcript_id": session.pending_transcript_id,
                    "text": session.pending_transcript_text,
                    "turn_no": session.pending_transcript_turn_no,
                    "message_id": session.pending_transcript_message_id,
                    "audio_url": session.pending_transcript_audio_url,
                    "is_final": True,
                },
            )

    @staticmethod
    def _restore_pending_transcript(session: VoiceSession) -> None:
        """从 Redis 恢复进程内不存在的转写草稿索引。"""
        if not session.require_transcript_confirmation or session.pending_transcript_id:
            return
        transcript_id = session.redis.get(
            f"{TRANSCRIPT_PENDING_KEY_PREFIX}{session.session_no}"
        )
        if not transcript_id:
            return
        transcript_id = str(transcript_id)
        draft = session.redis.get(
            f"voice_transcript_draft:{session.session_no}:{transcript_id}"
        )
        if not isinstance(draft, dict):
            session.redis.delete(
                f"{TRANSCRIPT_PENDING_KEY_PREFIX}{session.session_no}"
            )
            return
        session.pending_transcript_id = transcript_id
        session.pending_transcript_text = str(draft.get("text") or "")
        session.pending_transcript_turn_no = int(draft.get("turn_no") or 0)
        session.pending_transcript_message_id = str(
            draft.get("message_id") or ""
        ) or None
        session.pending_transcript_audio_url = str(
            draft.get("audio_url") or ""
        ) or None

    async def detach(self, session: VoiceSession, websocket: WebSocket) -> None:
        """解绑患者端；保留上游连接一段宽限期以支持重连。"""
        session.connected_clients.discard(websocket)
        if not session.connected_clients and not session.closed:
            async def delayed_close() -> None:
                try:
                    await asyncio.sleep(VOICE_GRACE_SECONDS)
                    if not session.connected_clients:
                        await self.close(session.session_no)
                except asyncio.CancelledError:
                    return

            session.close_task = asyncio.create_task(delayed_close())

    async def append_audio(self, session: VoiceSession, data: bytes) -> None:
        """接收患者 PCM 音频帧并转发上游。"""
        if session.closed:
            raise RuntimeError("语音会话已关闭")
        if session.turn_detection == "server_vad":
            target = (
                session.input_audio
                if session.speech_active
                else session.input_pre_roll
            )
            target.extend(data)
            if session.speech_active and len(target) > MAX_AUDIO_BUFFER_BYTES:
                raise ValueError("单轮语音长度超过系统限制")
            if not session.speech_active and len(target) > INPUT_PRE_ROLL_BYTES:
                del target[:-INPUT_PRE_ROLL_BYTES]
        else:
            if len(session.input_audio) + len(data) > MAX_AUDIO_BUFFER_BYTES:
                raise ValueError("单轮语音长度超过系统限制")
            session.input_audio.extend(data)
        await session.client.append_audio(data)

    async def commit(self, session: VoiceSession) -> None:
        """提交患者一轮语音。"""
        if session.turn_detection == "server_vad":
            raise ValueError("server_vad 模式由服务端自动提交语音轮次")
        if not session.input_audio:
            raise ValueError("当前没有可提交的语音")
        if session.input_committed:
            return
        session.input_turn_no, session.input_message_id = self._next_patient_message(
            session.session_no
        )
        session.input_committed = True
        session.transcript_received = False
        session.response_requested = False
        await self._persist_patient_audio(session)
        await self._broadcast_state(session, "transcribing")
        await session.client.commit_audio()

    async def interrupt(self, session: VoiceSession) -> None:
        """取消当前模型响应并停止客户端播放。"""
        session.audio_suppressed = True
        await session.client.cancel_response()

    async def confirm_transcript(self, session: VoiceSession, transcript_id: str) -> None:
        """确认患者可见的转写草稿后，才写正式消息并派发结构化处理。"""
        if session.confirmed_transcript_id == transcript_id:
            return
        if session.pending_transcript_id != transcript_id:
            draft = session.redis.get(
                f"voice_transcript_draft:{session.session_no}:{transcript_id}"
            )
            if isinstance(draft, dict):
                session.pending_transcript_id = transcript_id
                session.pending_transcript_text = str(draft.get("text") or "")
                session.pending_transcript_turn_no = int(draft.get("turn_no") or 0)
                session.pending_transcript_message_id = str(
                    draft.get("message_id") or ""
                ) or None
                session.pending_transcript_audio_url = str(
                    draft.get("audio_url") or ""
                ) or None
            else:
                raise ValueError("转写草稿不存在或已过期")
        text = session.pending_transcript_text or ""
        if not text:
            raise ValueError("转写草稿为空")
        await self._commit_transcript(session, text)
        session.confirmed_transcript_id = transcript_id
        session.pending_transcript_id = None
        session.pending_transcript_text = None
        session.pending_transcript_turn_no = 0
        session.pending_transcript_message_id = None
        session.pending_transcript_audio_url = None
        session.redis.delete(
            f"voice_transcript_draft:{session.session_no}:{transcript_id}"
        )
        session.redis.delete(
            f"{TRANSCRIPT_PENDING_KEY_PREFIX}{session.session_no}"
        )
        await self._broadcast_json(
            session,
            {"type": "transcript_confirmed", "transcript_id": transcript_id},
        )

    async def retry_transcript(self, session: VoiceSession, transcript_id: str) -> None:
        """废弃旧草稿并清理当前音频，等待患者重新录制。"""
        if transcript_id in session.discarded_transcript_ids:
            return
        if session.pending_transcript_id not in {None, transcript_id}:
            raise ValueError("转写草稿已被新的录音替换")
        if session.pending_transcript_id is None:
            draft = session.redis.get(
                f"voice_transcript_draft:{session.session_no}:{transcript_id}"
            )
            if not isinstance(draft, dict):
                raise ValueError("转写草稿不存在或已过期")
        session.pending_transcript_id = None
        session.pending_transcript_text = None
        session.pending_transcript_turn_no = 0
        session.pending_transcript_message_id = None
        session.pending_transcript_audio_url = None
        session.discarded_transcript_ids.add(transcript_id)
        session.redis.delete(
            f"voice_transcript_draft:{session.session_no}:{transcript_id}"
        )
        session.redis.delete(
            f"{TRANSCRIPT_PENDING_KEY_PREFIX}{session.session_no}"
        )
        session.transcript_received = False
        session.input_audio.clear()
        session.input_pre_roll.clear()
        session.input_committed = False
        session.input_message_id = None
        session.input_audio_url = None
        session.input_turn_no = 0
        await self._broadcast_json(
            session,
            {"type": "transcript_discarded", "transcript_id": transcript_id},
        )
        await self._broadcast_state(session, "listening")

    async def close(self, session_no: str) -> None:
        """关闭业务会话和上游连接。"""
        async with self._lock:
            session = self._sessions.pop(session_no, None)
        if session is None or session.closed:
            return
        session.closed = True
        if session.receive_task is not None:
            session.receive_task.cancel()
        if session.recovery_task is not None:
            session.recovery_task.cancel()
            session.recovery_task = None
        if session.manual_review_completion_task is not None:
            session.manual_review_completion_task.cancel()
            session.manual_review_completion_task = None
        await session.client.close()
        for websocket in list(session.connected_clients):
            await self._send_json(websocket, {"type": "closed"})

    async def _consume_upstream(self, session: VoiceSession) -> None:
        """消费 Qwen 上游事件。"""
        try:
            async for event in session.client.events():
                await self._handle_event(session, event)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("实时语音上游消费失败: session=%s", session.session_no)
            session.publisher.publish(
                AgentErrorEvent(
                    session_id=session.session_no,
                    task_id=session.task_id,
                    agent_name="voice_gateway",
                    error_code="VOICE_UPSTREAM_FAILED",
                    message="实时语音模型连接异常，后台正在尝试恢复",
                    retrying=True,
                )
            )
            await self._broadcast_json(
                session,
                {
                    "type": "error",
                    "code": "VOICE_UPSTREAM_FAILED",
                    "message": "实时语音模型连接异常，已保留文字输入",
                },
            )

    async def _handle_event(self, session: VoiceSession, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "input_audio_buffer.speech_started":
            await self._handle_speech_started(session)
            return
        if event_type == "input_audio_buffer.speech_stopped":
            await self._handle_speech_stopped(session)
            return
        if event_type == "conversation.item.input_audio_transcription.completed":
            await self._handle_patient_transcript(
                session,
                str(event.get("transcript") or "").strip(),
            )
            return
        if event_type == "response.created":
            response = event.get("response") or {}
            if session.pending_tool_responses > 0:
                session.pending_tool_responses = 0
                session.response_create_pending = False
            session.response_create_attempts = 0
            session.response_requested = True
            session.response_cancel_requested = False
            session.responding = True
            session.audio_suppressed = False
            session.current_response_id = str(response.get("id") or "") or None
            if session.current_response_id:
                session.active_response_ids.add(session.current_response_id)
                session.suppressed_response_ids.discard(session.current_response_id)
            await self._start_generation(
                session,
                response_id=session.current_response_id,
            )
            await self._broadcast_state(session, "thinking")
            return
        if event_type in {"response.text.delta", "response.audio_transcript.delta"}:
            await self._handle_text_delta(
                session,
                str(event.get("delta") or ""),
                source="audio_transcript"
                if event_type == "response.audio_transcript.delta"
                else "text",
                response_id=str(event.get("response_id") or "") or None,
            )
            return
        if event_type == "response.audio.delta":
            raw = base64.b64decode(str(event.get("delta") or ""))
            await self._handle_audio_delta(
                session,
                raw,
                response_id=str(event.get("response_id") or "") or None,
            )
            return
        if event_type == "response.audio.delta.binary":
            await self._handle_audio_delta(
                session,
                bytes(event.get("audio") or b""),
                response_id=str(event.get("response_id") or "") or None,
            )
            return
        if event_type == "response.function_call_arguments.done":
            await self._handle_tool_call(
                session,
                call_id=str(event.get("call_id") or ""),
                name=str(event.get("name") or ""),
                arguments=event.get("arguments") or "{}",
                response_id=str(event.get("response_id") or "") or None,
            )
            return
        if event_type == "response.audio_transcript.done":
            transcript = str(event.get("transcript") or "")
            generation = self._generation_for_event(
                session,
                str(event.get("response_id") or "") or None,
            )
            if transcript and generation is not None:
                generation.text = transcript
            return
        if event_type == "response.done":
            response = event.get("response") or {}
            status = str(response.get("status") or event.get("status") or "")
            response_id = (
                str(response.get("id") or event.get("response_id") or "") or None
            )
            if status == "cancelled":
                await self._cancel_generation(session, response_id=response_id)
            else:
                await self._complete_generation(session, response_id=response_id)
            return
        if event_type == "error":
            error = event.get("error") or {}
            if self._is_no_active_response_error(error):
                # response.cancel / response.create 与上游 response.done 可能乱序。
                # 该错误不代表语音会话失效，清理本地过期响应状态后继续监听。
                logger.warning(
                    "忽略可恢复的无活动响应竞态: session=%s code=%s message=%s",
                    session.session_no,
                    error.get("code"),
                    error.get("message"),
                )
                session.active_response_ids.clear()
                session.generations.clear()
                session.current_generation = None
                session.current_response_id = None
                session.responding = False
                session.response_requested = False
                session.response_cancel_requested = False
                session.audio_suppressed = False
                if session.pending_tool_responses > 0:
                    session.response_create_pending = True
                await self._broadcast_state(session, "listening")
                await self._maybe_create_response(session)
                return
            session.publisher.publish(
                AgentErrorEvent(
                    session_id=session.session_no,
                    task_id=session.task_id,
                    agent_name="qwen_realtime",
                    error_code=str(error.get("code") or "VOICE_MODEL_ERROR"),
                    message=str(error.get("message") or "实时语音模型调用失败"),
                    retrying=True,
                    generation_id=(
                        session.current_generation.generation_id
                        if session.current_generation
                        else None
                    ),
                )
            )
            await self._broadcast_json(
                session,
                {
                    "type": "error",
                    "code": str(error.get("code") or "VOICE_MODEL_ERROR"),
                    "message": str(error.get("message") or "实时语音模型调用失败"),
                },
            )

    async def _handle_speech_started(self, session: VoiceSession) -> None:
        """按官方 server_vad 事件开始一轮患者语音并处理打断。"""
        if session.speech_active:
            return
        if session.recovery_task is not None and not session.recovery_task.done():
            session.recovery_task.cancel()
            session.recovery_task = None
        if (
            session.recovery_mode_active
            and session.response_requested
            and not session.response_cancel_requested
        ):
            session.response_cancel_requested = True
            try:
                await session.client.cancel_response()
            except Exception:
                logger.exception(
                    "患者打断恢复模式响应时取消失败: session=%s",
                    session.session_no,
                )
        if session.pending_transcript_id:
            await self._broadcast_json(
                session,
                {
                    "type": "error",
                    "code": "TRANSCRIPT_CONFIRM_REQUIRED",
                    "message": "请先确认或重新录制当前转写",
                },
            )
            return
        session.speech_active = True
        session.input_turn_no, session.input_message_id = self._next_patient_message(
            session.session_no
        )
        session.input_audio = bytearray(session.input_pre_roll)
        session.input_pre_roll.clear()
        session.input_audio_url = None
        session.transcript_received = False
        session.pending_transcript_id = None
        session.pending_transcript_text = None
        session.pending_transcript_message_id = None
        session.pending_transcript_audio_url = None
        session.pending_transcript_turn_no = 0
        session.input_committed = False
        if not session.recovery_mode_active:
            await self._refresh_schedule_guidance(session)
        if session.responding and not session.response_cancel_requested:
            session.audio_suppressed = True
            if session.current_response_id:
                session.suppressed_response_ids.add(session.current_response_id)
            session.response_cancel_requested = True
            try:
                await session.client.cancel_response()
            except Exception:
                logger.exception(
                    "取消实时语音响应失败，继续接收患者当前语音: session=%s",
                    session.session_no,
                )
        await self._broadcast_json(session, {"type": "speech_started"})
        await self._broadcast_state(session, "listening")

    async def _handle_speech_stopped(self, session: VoiceSession) -> None:
        """按官方 server_vad 事件结束患者语音并保存当前轮原始音频。"""
        if not session.speech_active:
            return
        session.speech_active = False
        if session.input_audio and session.input_message_id:
            await self._persist_patient_audio(session)
        await self._broadcast_json(session, {"type": "speech_stopped"})
        await self._broadcast_state(session, "transcribing")

    async def _refresh_schedule_guidance(self, session: VoiceSession) -> None:
        """在当前患者发言结束前注入上一轮已经生成的 Schedule 指引。"""
        guidance = ScheduleTaskStore(session.redis).get_guidance(session.session_no)
        guidance_prompt = str(guidance.get("constraint_prompt") or "") if guidance else ""
        if not guidance_prompt:
            return
        lowered = guidance_prompt.lower()
        if (
            "宣教" in guidance_prompt
            or "get_education_material" in lowered
            or "teach-back" in lowered
        ):
            logger.info(
                "忽略已停用的主动宣教 Schedule 指引: session=%s",
                session.session_no,
            )
            return
        await session.client.update_instructions(
            session.instructions
            + (
                "\n\n当前轮必须遵守的业务约束：\n" + guidance_prompt
                if guidance_prompt
                else ""
            )
        )

    async def _handle_patient_transcript(self, session: VoiceSession, text: str) -> None:
        if not text or session.transcript_received:
            return
        session.transcript_received = True
        message_id = session.input_message_id or f"MSG-PATIENT-{uuid.uuid4().hex.upper()}"
        turn_no = session.input_turn_no or self._next_patient_message(session.session_no)[0]
        transcript_id = f"TRANSCRIPT-{uuid.uuid4().hex.upper()}"
        session.pending_transcript_id = transcript_id
        session.pending_transcript_text = text
        session.pending_transcript_turn_no = turn_no
        session.pending_transcript_message_id = message_id
        session.pending_transcript_audio_url = session.input_audio_url
        if session.require_transcript_confirmation:
            saved = session.redis.set(
                f"voice_transcript_draft:{session.session_no}:{transcript_id}",
                {
                    "text": text,
                    "turn_no": turn_no,
                    "message_id": message_id,
                    "audio_url": session.input_audio_url,
                },
                ex=TRANSCRIPT_DRAFT_TTL_SECONDS,
            )
            if not saved:
                await self._broadcast_json(
                    session,
                    {
                        "type": "error",
                        "code": "TRANSCRIPT_DRAFT_UNAVAILABLE",
                        "message": "转写暂时无法保存，请重新录制",
                    },
                )
                return
            pending_saved = session.redis.set(
                f"{TRANSCRIPT_PENDING_KEY_PREFIX}{session.session_no}",
                transcript_id,
                ex=TRANSCRIPT_DRAFT_TTL_SECONDS,
            )
            if not pending_saved:
                session.redis.delete(
                    f"voice_transcript_draft:{session.session_no}:{transcript_id}"
                )
                await self._broadcast_json(
                    session,
                    {
                        "type": "error",
                        "code": "TRANSCRIPT_DRAFT_UNAVAILABLE",
                        "message": "转写暂时无法保存，请重新录制",
                    },
                )
                return
            await self._broadcast_json(
                session,
                {
                    "type": "transcript_ready",
                    "transcript_id": transcript_id,
                    "text": text,
                    "turn_no": turn_no,
                    "message_id": message_id,
                    "audio_url": session.input_audio_url,
                    "is_final": True,
                },
            )
            return
        await self._commit_transcript(session, text)
        session.confirmed_transcript_id = transcript_id
        session.pending_transcript_id = None
        session.pending_transcript_text = None
        session.pending_transcript_turn_no = 0
        session.pending_transcript_message_id = None
        session.pending_transcript_audio_url = None

    async def _commit_transcript(self, session: VoiceSession, text: str) -> None:
        """把已确认转写写入正式历史并派发后台 Worker。"""
        message_id = session.pending_transcript_message_id or session.input_message_id or f"MSG-PATIENT-{uuid.uuid4().hex.upper()}"
        turn_no = session.pending_transcript_turn_no or session.input_turn_no or self._next_patient_message(session.session_no)[0]
        audio_url = session.pending_transcript_audio_url or session.input_audio_url
        history = DialogHistoryManager()
        await history.save_message(
            session.session_no,
            turn_no=turn_no,
            message_no=message_id,
            role_type="患者",
            message_type="语音",
            content_text=text,
            audio_url=audio_url,
            asr_text=text,
            creator="patient",
        )
        session.publisher.publish(
            PatientAnswerEvent(
                session_id=session.session_no,
                task_id=session.task_id,
                message_id=message_id,
                turn_number=turn_no,
                content=text,
                client_message_id=message_id,
                input_mode="voice",
            )
        )
        matches = get_keyword_matcher().match(text)
        constraint = "\n".join(
            item.constraint_prompt for item in matches if item.constraint_prompt
        )
        if constraint:
            instruction_base = (
                session.client.instructions
                if session.recovery_mode_active
                else session.instructions
            )
            await session.client.update_instructions(
                instruction_base
                + "\n\n当前轮必须遵守的业务约束：\n"
                + constraint
            )
        dispatch_voice_answer_workers(
            session.session_no,
            task_id=session.task_id,
            scale_codes=session.scale_codes,
            source_message_id=message_id,
            source_event_id=None,
            patient_info=session.patient_info,
        )
        if session.recovery_mode_active:
            session.recovery_source_message_no = message_id
            session.recovery_answer_response_pending = True
            self._schedule_recovery_progress(
                session,
                source_message_no=message_id,
            )
        session.input_audio.clear()
        session.input_committed = False
        session.input_message_id = None
        session.input_audio_url = None
        session.input_turn_no = 0
        if (
            session.turn_detection != "server_vad"
            and not session.response_requested
        ):
            session.response_requested = True
            await session.client.create_response()

    async def _start_generation(
        self,
        session: VoiceSession,
        *,
        response_id: str | None = None,
    ) -> None:
        if response_id and response_id in session.generations:
            session.current_generation = session.generations[response_id]
            return
        if (
            response_id is None
            and session.current_generation is not None
            and not session.current_generation.completed
        ):
            return
        turn_no = (session.input_turn_no or self._next_patient_message(session.session_no)[0]) + 1
        generation_id = f"GEN-VOICE-{uuid.uuid4().hex.upper()}"
        message_id = f"MSG-AI-{uuid.uuid4().hex.upper()}"
        generation = VoiceGeneration(
            generation_id=generation_id,
            message_id=message_id,
            turn_no=turn_no,
            response_id=response_id,
            is_recovery=(
                session.recovery_mode_active
                or session.next_response_is_recovery
            ),
            is_manual_review_completion=(
                session.next_response_is_manual_review_completion
            ),
        )
        session.next_response_is_recovery = False
        session.next_response_is_manual_review_completion = False
        session.current_generation = generation
        if response_id:
            session.generations[response_id] = generation

    @staticmethod
    def _generation_for_event(
        session: VoiceSession,
        response_id: str | None,
    ) -> VoiceGeneration | None:
        """按供应商响应编号定位生成，兼容事件缺少 response_id 的旧事件。"""
        if response_id:
            return session.generations.get(response_id)
        return session.current_generation

    @staticmethod
    def _ensure_generation_started(
        session: VoiceSession,
        generation: VoiceGeneration,
    ) -> None:
        """首个患者可见增量到达时再发布占位，避免 Function Call 空消息。"""
        if generation.started_event_id is not None:
            return
        generation.started_event_id = session.publisher.publish(
            AssistantMessageStartedEvent(
                session_id=session.session_no,
                task_id=session.task_id,
                message_id=generation.message_id,
                turn_number=generation.turn_no,
                generation_id=generation.generation_id,
            )
        )

    async def _handle_text_delta(
        self,
        session: VoiceSession,
        delta: str,
        *,
        source: str,
        response_id: str | None = None,
    ) -> None:
        if not delta:
            return
        generation = self._generation_for_event(session, response_id)
        if generation is None:
            if response_id:
                return
            await self._start_generation(
                session,
                response_id=response_id or session.current_response_id,
            )
            generation = self._generation_for_event(
                session,
                response_id or session.current_response_id,
            )
        assert generation is not None
        self._ensure_generation_started(session, generation)
        if generation.text_source is None:
            generation.text_source = source
        if generation.text_source != source:
            return
        generation.text += delta
        session.publisher.publish(
            DialogTextEvent(
                session_id=session.session_no,
                task_id=session.task_id,
                message_id=generation.message_id,
                turn_number=generation.turn_no,
                text_chunk=delta,
                generation_id=generation.generation_id,
                is_final=False,
            )
        )

    async def _handle_audio_delta(
        self,
        session: VoiceSession,
        audio: bytes,
        *,
        response_id: str | None = None,
    ) -> None:
        if not audio:
            return
        generation = self._generation_for_event(session, response_id)
        if generation is None:
            if response_id:
                return
            await self._start_generation(
                session,
                response_id=response_id or session.current_response_id,
            )
            generation = self._generation_for_event(
                session,
                response_id or session.current_response_id,
            )
        assert generation is not None
        if session.audio_suppressed or (
            response_id and response_id in session.suppressed_response_ids
        ):
            return
        self._ensure_generation_started(session, generation)
        generation.audio.extend(audio)
        generation.all_audio.extend(audio)
        await self._broadcast_state(session, "speaking")
        await self._broadcast_json(
            session,
            {
                "type": "audio",
                "sequence": generation.audio_segment_no,
                "sample_rate": generation.sample_rate,
                "audio_base64": base64.b64encode(audio).decode("ascii"),
            },
        )
        # 每约 1 秒音频保存一个分片，监控端可从 SSE 索引播放。
        if len(generation.audio) >= 48_000:
            await self._flush_audio_segment(session, generation)

    async def _flush_audio_segment(self, session: VoiceSession, generation: VoiceGeneration) -> None:
        if not generation.audio:
            return
        data = bytes(generation.audio)
        generation.audio.clear()
        filename = f"segment-{generation.audio_segment_no:06d}.wav"
        url = session.audio_store.save_wav(
            session_no=session.session_no,
            generation_id=generation.generation_id,
            filename=filename,
            data=data,
            sample_rate=generation.sample_rate,
        )
        event = DialogAudioEvent(
            session_id=session.session_no,
            task_id=session.task_id,
            message_id=generation.message_id,
            turn_number=generation.turn_no,
            audio_url=url,
            audio_format=generation.audio_format,
            role="assistant",
            generation_id=generation.generation_id,
            segment_no=generation.audio_segment_no,
            sample_rate=generation.sample_rate,
            is_final=False,
        )
        generation.audio_segment_no += 1
        session.publisher.publish(event)

    async def _complete_generation(
        self,
        session: VoiceSession,
        *,
        response_id: str | None = None,
    ) -> None:
        generation = self._generation_for_event(session, response_id)
        if generation is None or generation.completed:
            return
        if response_id and generation.response_id and response_id != generation.response_id:
            return
        if not generation.text and not generation.all_audio:
            self._remove_generation(session, generation)
            if generation.is_recovery and session.recovery_source_message_no is not None:
                session.recovery_answer_response_pending = False
            session.response_requested = False
            session.response_cancel_requested = False
            if not session.closed:
                await self._broadcast_state(session, "listening")
                await self._maybe_create_response(session)
            return
        generation.completed = True
        closing_candidate = (
            not generation.is_recovery
            and not generation.is_manual_review_completion
            and VoiceTurnGuard.has_closing_intent(generation.text)
        )
        await self._flush_audio_segment(session, generation)
        audio_url: str | None = None
        if generation.all_audio:
            audio_url = session.audio_store.save_wav(
                session_no=session.session_no,
                generation_id=generation.generation_id,
                filename="assistant.wav",
                data=bytes(generation.all_audio),
                sample_rate=generation.sample_rate,
            )
        history = DialogHistoryManager()
        await history.save_message(
            session.session_no,
            turn_no=generation.turn_no,
            message_no=generation.message_id,
            role_type="AI",
            message_type="语音",
            content_text=generation.text,
            audio_url=audio_url,
            tts_text=generation.text,
            creator="dialog_agent_voice",
        )
        session.publisher.publish(
            DialogMessageEvent(
                session_id=session.session_no,
                task_id=session.task_id,
                message_id=generation.message_id,
                turn_number=generation.turn_no,
                role="assistant",
                content=generation.text,
                generation_id=generation.generation_id,
            )
        )
        if audio_url:
            session.publisher.publish(
                DialogAudioEvent(
                    session_id=session.session_no,
                    task_id=session.task_id,
                    message_id=generation.message_id,
                    turn_number=generation.turn_no,
                    audio_url=audio_url,
                    audio_format="wav",
                    role="assistant",
                    generation_id=generation.generation_id,
                    segment_no=max(generation.audio_segment_no - 1, 0),
                    sample_rate=generation.sample_rate,
                    is_final=True,
                )
            )
        self._remove_generation(session, generation)
        if generation.is_recovery and session.recovery_source_message_no is not None:
            session.recovery_answer_response_pending = False
        session.response_requested = False
        session.response_cancel_requested = False
        if not session.responding and session.pending_tool_responses == 0:
            await self._broadcast_json(
                session,
                {
                    "type": "response_completed",
                    "response_id": generation.response_id,
                },
            )
            from app.services.voice_completion_service import (
                mark_voice_response_completed,
            )

            await asyncio.to_thread(
                mark_voice_response_completed,
                session_id=session.session_no,
                task_id=session.task_id,
                response_turn=generation.turn_no,
                response_id=generation.response_id,
                generation_id=generation.generation_id,
                is_manual_review_completion=(
                    generation.is_manual_review_completion
                ),
                redis=session.redis,
            )
            if (
                not generation.is_recovery
                and not generation.is_manual_review_completion
                and int(session.patient_info.get("manual_review_count") or 0) > 0
            ):
                self._schedule_manual_review_completion_after_extraction(session)
        if generation.is_recovery:
            pass
        elif (
            closing_candidate
            and not session.closed
            and not session.responding
            and session.pending_tool_responses == 0
        ):
            self._schedule_premature_close_recovery(
                session,
                response_id=generation.response_id,
            )
        if not session.closed:
            await self._broadcast_state(session, "listening")
            await self._maybe_create_response(session)

    async def _cancel_generation(
        self,
        session: VoiceSession,
        *,
        response_id: str | None = None,
    ) -> None:
        """处理官方 response.done(status=cancelled)，丢弃未完成响应。"""
        generation = self._generation_for_event(session, response_id)
        if generation is not None:
            if (
                response_id
                and generation.response_id
                and response_id != generation.response_id
            ):
                return
            self._remove_generation(session, generation)
            if generation.is_recovery and session.recovery_source_message_no is not None:
                session.recovery_answer_response_pending = False
        session.response_requested = False
        session.response_cancel_requested = False
        await self._broadcast_json(session, {"type": "interrupted"})
        await self._broadcast_state(session, "listening")
        if (
            generation is not None
            and generation.is_manual_review_completion
            and not session.closed
        ):
            self._schedule_manual_review_completion_after_extraction(session)
        await self._maybe_create_response(session)

    @staticmethod
    def _remove_generation(
        session: VoiceSession,
        generation: VoiceGeneration,
    ) -> None:
        """从响应索引中移除已完成/取消的生成，并切换到仍活跃的响应。"""
        if generation.response_id:
            session.generations.pop(generation.response_id, None)
            session.active_response_ids.discard(generation.response_id)
        if session.current_generation is generation:
            session.current_generation = next(
                iter(session.generations.values()),
                None,
            )
        if session.current_response_id == generation.response_id:
            session.current_response_id = (
                next(iter(session.generations), None)
            )
        session.responding = bool(session.active_response_ids)

    def _schedule_manual_review_completion_after_extraction(
        self,
        session: VoiceSession,
    ) -> None:
        """每轮普通回复后等待 Extraction，完成时补一条专门人工审核结束播报。"""
        existing = session.manual_review_completion_task
        if existing is not None and not existing.done():
            existing.cancel()
        session.manual_review_completion_task = asyncio.create_task(
            self._announce_manual_review_after_extraction(session)
        )

    async def _announce_manual_review_after_extraction(
        self,
        session: VoiceSession,
    ) -> None:
        """等待当前患者答案入库；仅在 AI 可采集题全部完成后触发结束播报。"""
        current_task = asyncio.current_task()
        try:
            source_message_no = await asyncio.to_thread(
                VoiceTurnGuard.latest_patient_message_no,
                session.session_no,
            )
            if not source_message_no:
                return
            waited = 0.0
            while not VoiceTurnGuard.extraction_processed(
                session.redis,
                session.session_no,
                source_message_no,
            ):
                if session.closed:
                    return
                if waited >= VOICE_CLOSE_RECOVERY_TIMEOUT_SECONDS:
                    logger.warning(
                        "人工审核结束播报等待 Extraction 超时: session=%s source=%s",
                        session.session_no,
                        source_message_no,
                    )
                    return
                await asyncio.sleep(VOICE_CLOSE_RECOVERY_POLL_SECONDS)
                waited += VOICE_CLOSE_RECOVERY_POLL_SECONDS

            decision = await asyncio.to_thread(
                VoiceTurnGuard.build_recovery_decision,
                session.session_no,
                session.task_list,
            )
            if not decision.progress.completed:
                return
            await self._start_manual_review_completion_response(session)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(
                "人工审核结束播报触发失败，保留语音会话等待重试: session=%s",
                session.session_no,
            )
        finally:
            if session.manual_review_completion_task is current_task:
                session.manual_review_completion_task = None

    async def _start_manual_review_completion_response(
        self,
        session: VoiceSession,
    ) -> None:
        """通知责任护士后，创建唯一有资格跨越最终完成屏障的 Qwen 响应。"""
        configured_count = int(session.patient_info.get("manual_review_count") or 0)
        if configured_count <= 0 or session.closed:
            return
        notification = await asyncio.to_thread(
            ensure_planned_manual_review_notification,
            session.session_no,
        )
        if notification.item_count <= 0 or not notification.notified:
            logger.error(
                "固定人工审核通知未就绪，拒绝创建结束播报: session=%s",
                session.session_no,
            )
            return

        waited = 0.0
        while (
            session.speech_active
            or session.responding
            or session.active_response_ids
            or session.response_requested
            or session.pending_tool_responses > 0
        ):
            if session.closed:
                return
            if waited >= VOICE_CLOSE_RECOVERY_TIMEOUT_SECONDS:
                logger.warning(
                    "人工审核结束播报等待当前语音响应结束超时: session=%s",
                    session.session_no,
                )
                return
            await asyncio.sleep(VOICE_CLOSE_RECOVERY_POLL_SECONDS)
            waited += VOICE_CLOSE_RECOVERY_POLL_SECONDS

        await session.client.update_instructions(
            self._build_manual_review_completion_instructions(
                notification.item_count
            )
        )
        session.next_response_is_manual_review_completion = True
        session.response_requested = True
        try:
            await session.client.create_response()
        except Exception:
            session.response_requested = False
            session.next_response_is_manual_review_completion = False
            raise
        logger.info(
            "已创建固定人工审核专门结束播报: session=%s count=%s request=%s",
            session.session_no,
            notification.item_count,
            notification.request_id,
        )

    @staticmethod
    def _build_manual_review_completion_instructions(item_count: int) -> str:
        """专门结束播报只允许告知人工审核安排，不得生成新问题。"""
        return (
            "你是一名专业的AI护理助手。结构化AI问答已经完成。\n"
            "现在只允许向患者播报下面这一句话，不得增加任何问题、宣教、解释或其他内容：\n"
            f"本次AI问答已经完成，剩余{item_count}项固定内容需要护士人工审核；"
            "我已通知责任护士，请您稍候。\n"
            "播报完立即停止输出，等待系统结束会话。"
        )

    def _schedule_premature_close_recovery(
        self,
        session: VoiceSession,
        *,
        response_id: str | None,
    ) -> None:
        """异步安排提前结束恢复，不阻塞 Qwen 上游事件消费。"""
        if session.recovery_task is not None and not session.recovery_task.done():
            return
        session.recovery_task = asyncio.create_task(
            self._recover_premature_close(
                session,
                response_id=response_id,
            )
        )

    async def _recover_premature_close(
        self,
        session: VoiceSession,
        *,
        response_id: str | None,
    ) -> None:
        """等待当前患者答案抽取完成后，按权威进度自动纠正并补问一题。"""
        current_task = asyncio.current_task()
        try:
            source_message_no = await asyncio.to_thread(
                VoiceTurnGuard.latest_patient_message_no,
                session.session_no,
            )
            waited = 0.0
            while not VoiceTurnGuard.extraction_processed(
                session.redis,
                session.session_no,
                source_message_no,
            ):
                if (
                    session.closed
                    or session.speech_active
                    or session.responding
                    or session.response_requested
                ):
                    return
                if waited >= VOICE_CLOSE_RECOVERY_TIMEOUT_SECONDS:
                    logger.warning(
                        "提前结束恢复等待 Extraction 超时，保持当前会话继续监听: "
                        "session=%s source=%s response=%s",
                        session.session_no,
                        source_message_no,
                        response_id,
                    )
                    return
                await asyncio.sleep(VOICE_CLOSE_RECOVERY_POLL_SECONDS)
                waited += VOICE_CLOSE_RECOVERY_POLL_SECONDS

            decision = await asyncio.to_thread(
                VoiceTurnGuard.build_recovery_decision,
                session.session_no,
                session.task_list,
            )
            if not decision.should_recover or decision.next_question is None:
                return
            if (
                session.closed
                or session.speech_active
                or session.responding
                or session.response_requested
            ):
                return

            recovery_instructions = self._build_recovery_question_instructions(
                session.patient_info,
                decision.next_question,
                mode_label="提前结束恢复模式",
                transition_rule=(
                    "先用一句自然、简短的话纠正刚才过早结束，"
                    "然后立即询问下面这一项。"
                ),
            )
            await session.client.update_instructions(recovery_instructions)
            session.recovery_mode_active = True
            session.recovery_current_question_id = decision.next_question.question_id
            session.recovery_source_message_no = None
            session.recovery_answer_response_pending = False
            session.recovery_instruction_active = True
            session.next_response_is_recovery = True
            session.response_requested = True
            try:
                await session.client.create_response()
            except Exception:
                session.response_requested = False
                session.next_response_is_recovery = False
                await self._restore_base_instructions(session)
                raise
            logger.warning(
                "检测到语音模型提前结束，已触发自动补问: "
                "session=%s response=%s question_id=%s remaining=%s",
                session.session_no,
                response_id,
                decision.next_question.question_id,
                list(decision.progress.remaining_question_ids),
            )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(
                "提前结束自动恢复失败，不中断实时语音会话: session=%s",
                session.session_no,
            )
        finally:
            if session.recovery_task is current_task:
                session.recovery_task = None

    def _schedule_recovery_progress(
        self,
        session: VoiceSession,
        *,
        source_message_no: str,
    ) -> None:
        """恢复模式下等待本轮 Extraction 完成，再决定下一条 null 问题。"""
        if session.recovery_task is not None and not session.recovery_task.done():
            session.recovery_task.cancel()
        session.recovery_task = asyncio.create_task(
            self._advance_recovery_after_answer(
                session,
                source_message_no=source_message_no,
            )
        )

    async def _advance_recovery_after_answer(
        self,
        session: VoiceSession,
        *,
        source_message_no: str,
    ) -> None:
        """患者回答一个恢复问题后，仅从最新 remaining 中选择下一题。"""
        current_task = asyncio.current_task()
        try:
            waited = 0.0
            while not VoiceTurnGuard.extraction_processed(
                session.redis,
                session.session_no,
                source_message_no,
            ):
                if (
                    session.closed
                    or not session.recovery_mode_active
                    or session.recovery_source_message_no != source_message_no
                ):
                    return
                if waited >= VOICE_CLOSE_RECOVERY_TIMEOUT_SECONDS:
                    logger.warning(
                        "恢复模式等待 Extraction 超时: session=%s source=%s",
                        session.session_no,
                        source_message_no,
                    )
                    return
                await asyncio.sleep(VOICE_CLOSE_RECOVERY_POLL_SECONDS)
                waited += VOICE_CLOSE_RECOVERY_POLL_SECONDS

            decision = await asyncio.to_thread(
                VoiceTurnGuard.build_recovery_decision,
                session.session_no,
                session.task_list,
            )
            if decision.progress.completed:
                await self._finish_recovery_mode(session)
                return
            if decision.next_question is None:
                logger.error(
                    "恢复模式存在未完成问题但无法映射到 Task-todo，禁止退回完整题表: "
                    "session=%s remaining=%s",
                    session.session_no,
                    list(decision.progress.remaining_question_ids),
                )
                return

            waited = 0.0
            while (
                session.recovery_answer_response_pending
                or session.responding
                or session.active_response_ids
                or session.response_requested
                or session.speech_active
            ):
                if (
                    session.closed
                    or not session.recovery_mode_active
                    or session.recovery_source_message_no != source_message_no
                ):
                    return
                if waited >= VOICE_CLOSE_RECOVERY_TIMEOUT_SECONDS:
                    logger.warning(
                        "恢复模式等待当前语音响应结束超时: session=%s source=%s",
                        session.session_no,
                        source_message_no,
                    )
                    return
                await asyncio.sleep(VOICE_CLOSE_RECOVERY_POLL_SECONDS)
                waited += VOICE_CLOSE_RECOVERY_POLL_SECONDS

            recovery_instructions = self._build_recovery_question_instructions(
                session.patient_info,
                decision.next_question,
                mode_label="持续恢复模式",
                transition_rule=(
                    "直接自然过渡到下面这一项，不要解释系统状态，"
                    "也不要重复道歉。"
                ),
            )
            await session.client.update_instructions(recovery_instructions)
            session.recovery_current_question_id = decision.next_question.question_id
            session.recovery_source_message_no = None
            session.recovery_instruction_active = True
            session.next_response_is_recovery = True
            session.response_requested = True
            try:
                await session.client.create_response()
            except Exception:
                session.response_requested = False
                session.next_response_is_recovery = False
                raise
            logger.info(
                "恢复模式继续补问下一条未完成问题: session=%s question_id=%s remaining=%s",
                session.session_no,
                decision.next_question.question_id,
                list(decision.progress.remaining_question_ids),
            )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(
                "恢复模式推进失败，保留当前恢复提示等待下一轮: session=%s",
                session.session_no,
            )
        finally:
            if session.recovery_task is current_task:
                session.recovery_task = None

    @staticmethod
    def _build_recovery_question_instructions(
        patient_info: dict[str, Any],
        question: QuestionTask,
        *,
        mode_label: str,
        transition_rule: str,
    ) -> str:
        """构建只暴露一个 remaining/null 问题的恢复提示词。

        提前结束恢复与重新进入旧会话共用此入口，避免任何恢复路径重新把完整
        Task-todo 暴露给 Qwen。
        """
        patient_name = str(patient_info.get("name") or "患者")
        patient_age = patient_info.get("age")
        patient_gender = str(patient_info.get("gender") or "未知")
        patient_context = (
            f"患者姓名：{patient_name}；"
            f"性别：{patient_gender}；"
            f"年龄：{patient_age if patient_age is not None else '未知'}。"
        )
        return (
            f"你是一名专业的AI护理助手。当前处于【{mode_label}】。\n\n"
            f"【患者上下文】\n{patient_context}\n\n"
            "【恢复规则】\n"
            "1. 不要重新自我介绍，不要重新开始整套评估。\n"
            "2. 当前只允许处理下面这一项。除这一项外，不得提出任何其他问题。\n"
            "3. 已经有结构化答案的问题全部视为完成，不得重复询问、核对或换一种说法再问。\n"
            "4. 不得根据此前完整任务信息、历史问题或常识自行选择其他问题。\n"
            f"5. {transition_rule}\n"
            "6. 患者回答当前问题后，只做非常简短的确认；在系统更新当前问题之前，"
            "不得重复本题，也不得提出新的问题。\n"
            "7. 一次只问一个问题，不得朗读内部题号、数据库状态、null、remaining 或进度字段。\n"
            "8. 主动健康教育已关闭，不得主动扩展宣教、风险教育或 teach-back。\n"
            "9. 不得自行宣布评估完成或结束，等待系统完成状态。\n\n"
            "【当前唯一允许询问的问题】\n"
            f"{question.patient_text}\n"
        )

    @staticmethod
    def _build_recovery_mapping_error_instructions() -> str:
        """remaining 与 Task-todo 映射异常时宁可停问，也不能回退完整题表。"""
        return (
            "你是一名专业的AI护理助手。当前评估存在未完成结构化项目，"
            "但系统暂时无法安全确定下一道允许询问的问题。"
            "在系统更新指令前，不得询问任何新的量表问题，不得重复历史问题，"
            "不得自行展开健康教育或宣布评估完成。"
        )

    @staticmethod
    def _build_completed_wait_instructions() -> str:
        """重新进入已结构化完成的会话时禁止继续问卷。"""
        return (
            "你是一名专业的AI护理助手。结构化评估已经确认完成。"
            "不得再询问任何量表问题，不得重复核对历史问题，也不要开启新的评估话题；"
            "如患者继续说话，只做简短礼貌回应并等待系统结束会话。"
        )

    async def _finish_recovery_mode(self, session: VoiceSession) -> None:
        """全部 remaining 清空后停止提问；有固定审核时追加专门结束播报。"""
        try:
            if int(session.patient_info.get("manual_review_count") or 0) > 0:
                await self._start_manual_review_completion_response(session)
            else:
                await session.client.update_instructions(
                    self._build_completed_wait_instructions()
                )
        finally:
            session.recovery_instruction_active = False
            session.recovery_mode_active = False
            session.recovery_current_question_id = None
            session.recovery_source_message_no = None
            session.recovery_answer_response_pending = False
            session.next_response_is_recovery = False

    async def _restore_base_instructions(self, session: VoiceSession) -> None:
        """退出恢复模式并恢复长期基础提示词。"""
        if not session.recovery_instruction_active and not session.recovery_mode_active:
            return
        try:
            await session.client.update_instructions(session.instructions)
        finally:
            session.recovery_instruction_active = False
            session.recovery_mode_active = False
            session.recovery_current_question_id = None
            session.recovery_source_message_no = None
            session.recovery_answer_response_pending = False
            session.next_response_is_recovery = False

    async def _handle_tool_call(
        self,
        session: VoiceSession,
        *,
        call_id: str,
        name: str,
        arguments: Any,
        response_id: str | None = None,
    ) -> None:
        if not call_id or not name:
            return
        if call_id in session.handled_tool_call_ids:
            logger.warning(
                "忽略重复语音工具调用: session=%s call_id=%s",
                session.session_no,
                call_id,
            )
            return
        session.handled_tool_call_ids.add(call_id)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        generation = self._generation_for_event(session, response_id)
        if generation is not None:
            generation.tool_call_only = True
        try:
            result = await execute_tool(name, arguments)
        except Exception:
            logger.exception("语音工具执行失败: session=%s tool=%s", session.session_no, name)
            result = {"success": False, "message": "工具执行失败"}
        session.publisher.publish(
            ToolCallEvent(
                session_id=session.session_no,
                task_id=session.task_id,
                message_id=(
                    generation.message_id
                    if generation
                    else None
                ),
                turn_number=(
                    generation.turn_no
                    if generation
                    else session.input_turn_no
                ),
                call_id=call_id,
                tool_name=name,
                tool_args=arguments,
                tool_result=result,
            )
        )
        publish_tool_result(
            session_no=session.session_no,
            task_id=session.task_id,
            message_no=(
                generation.message_id
                if generation
                else None
            ),
            tool_name=name,
            tool_args=arguments,
            tool_result=result,
            source_invocation_id=call_id,
            publisher=session.publisher,
        )
        await session.client.send_tool_result(call_id, result)
        # 多个 function call 只需要一个后续 response.create；等待当前工具响应
        # 完成后统一触发，避免快速停顿或工具链重入时重复创建响应。
        session.pending_tool_responses = 1
        session.response_create_pending = True
        await self._maybe_create_response(session)

    async def _persist_patient_audio(self, session: VoiceSession) -> None:
        if not session.input_message_id:
            return
        data = bytes(session.input_audio)
        url = session.audio_store.save_wav(
            session_no=session.session_no,
            generation_id=session.input_message_id,
            filename="patient.wav",
            data=data,
            sample_rate=16000,
        )
        session.input_audio_url = url
        duration_ms = int(len(data) / (16000 * 2) * 1000)
        session.publisher.publish(
            PatientAudioEvent(
                session_id=session.session_no,
                task_id=session.task_id,
                message_id=session.input_message_id,
                turn_number=session.input_turn_no,
                audio_url=url,
                audio_format="wav",
                duration_ms=duration_ms,
            )
        )

    async def _broadcast_state(self, session: VoiceSession, state: str) -> None:
        await self._broadcast_json(session, {"type": "state", "state": state})

    async def _broadcast_json(self, session: VoiceSession, payload: dict[str, Any]) -> None:
        for websocket in list(session.connected_clients):
            await self._send_json(websocket, payload)

    @staticmethod
    async def _send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
        try:
            await websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect):
            return

    @staticmethod
    def _next_patient_message(session_no: str) -> tuple[int, str]:
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            session_id = db.scalar(
                select(InteractionSession.id).where(
                    InteractionSession.session_no == session_no,
                    InteractionSession.deleted == 0,
                )
            )
            if session_id is None:
                raise RuntimeError("交互会话不存在")
            current_turn = db.scalar(
                select(func.max(InteractionMessage.turn_no)).where(
                    InteractionMessage.interaction_session_id == session_id,
                    InteractionMessage.role_type.in_(["AI", "assistant"]),
                    InteractionMessage.deleted == 0,
                )
            )
            return int(current_turn or 1), f"MSG-PATIENT-VOICE-{uuid.uuid4().hex.upper()}"


voice_gateway = VoiceGateway()
