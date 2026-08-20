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
from app.services.qwen_realtime_client import QwenRealtimeClient
from app.services.tool_interaction_service import publish_tool_result
from app.utils.redis_client import RedisClient, get_redis
from app.workers.event_publisher import DialogEventPublisher
from app.workers.schedule_task_store import ScheduleTaskStore

logger = logging.getLogger(__name__)


VOICE_GRACE_SECONDS = 180
MAX_AUDIO_BUFFER_BYTES = 12 * 1024 * 1024
INPUT_PRE_ROLL_BYTES = 32_000


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
    receive_task: Any | None = None
    close_task: Any | None = None
    closed: bool = False


class VoiceGateway:
    """进程内 Voice Gateway 注册表。

    业务事件和消息历史是持久化事实；本注册表只保留上游 WebSocket 和连接
    订阅者，进程重启后可以依据历史重新建立会话。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}
        self._lock = asyncio.Lock()

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
            plan = ScheduleTaskStore(get_redis()).get_plan(session_no)
            task_list = plan.tasks if plan is not None else []
            instructions = build_system_prompt(
                patient_info=patient_info,
                task_list=task_list,
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
                instructions=instructions,
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
                instructions=instructions,
                client=client,
                redis=get_redis(),
                audio_store=DialogAudioStore(),
                publisher=DialogEventPublisher(session_no),
                turn_detection=turn_detection,
            )
            self._sessions[session_no] = gateway_session
            gateway_session.receive_task = asyncio.create_task(
                self._consume_upstream(gateway_session)
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

    async def close(self, session_no: str) -> None:
        """关闭业务会话和上游连接。"""
        async with self._lock:
            session = self._sessions.pop(session_no, None)
        if session is None or session.closed:
            return
        session.closed = True
        if session.receive_task is not None:
            session.receive_task.cancel()
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
                session.pending_tool_responses -= 1
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
        session.speech_active = True
        session.input_turn_no, session.input_message_id = self._next_patient_message(
            session.session_no
        )
        session.input_audio = bytearray(session.input_pre_roll)
        session.input_pre_roll.clear()
        session.input_audio_url = None
        session.transcript_received = False
        session.input_committed = False
        await self._refresh_schedule_guidance(session)
        if session.responding:
            session.audio_suppressed = True
            if session.current_response_id:
                session.suppressed_response_ids.add(session.current_response_id)
            await session.client.cancel_response()
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
        history = DialogHistoryManager()
        await history.save_message(
            session.session_no,
            turn_no=turn_no,
            message_no=message_id,
            role_type="患者",
            message_type="语音",
            content_text=text,
            audio_url=session.input_audio_url,
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
            await session.client.update_instructions(
                session.instructions
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
        )
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
            session.response_requested = False
            if not session.closed:
                await self._broadcast_state(session, "listening")
            return
        generation.completed = True
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
        session.response_requested = False
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
                redis=session.redis,
            )
        if not session.closed:
            await self._broadcast_state(session, "listening")

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
        session.response_requested = False
        await self._broadcast_json(session, {"type": "interrupted"})
        await self._broadcast_state(session, "listening")

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
            publisher=session.publisher,
        )
        await session.client.send_tool_result(call_id, result)
        session.pending_tool_responses += 1
        await session.client.create_response()

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
