from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.voice_gateway as voice_gateway_module
from app.schemas.events import (
    DialogMessageEvent,
    PatientAnswerEvent,
    PatientAudioEvent,
    ToolCallEvent,
)
from app.services.dialog_audio_store import DialogAudioStore
from app.services.voice_gateway import (
    VoiceGateway,
    VoiceGeneration,
    VoiceSession,
)


class FakeClient:
    def __init__(self) -> None:
        self.appended: list[bytes] = []
        self.commit_audio = AsyncMock()
        self.create_response = AsyncMock()
        self.cancel_response = AsyncMock()
        self.update_instructions = AsyncMock()
        self.send_tool_result = AsyncMock()

    async def append_audio(self, data: bytes) -> None:
        self.appended.append(data)


class FakePublisher:
    def __init__(self) -> None:
        self.events: list = []

    def publish(self, event):
        self.events.append(event)
        return f"{len(self.events)}-0"


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class FakeRedis:
    def get(self, _key: str):
        return None


def make_session(tmp_path: Path) -> VoiceSession:
    return VoiceSession(
        session_no="SESS-VOICE",
        task_id=1,
        patient_id=2,
        patient_info={"name": "患者"},
        scale_codes=["scale"],
        instructions="基础提示词",
        client=FakeClient(),
        redis=FakeRedis(),
        audio_store=DialogAudioStore(tmp_path),
        publisher=FakePublisher(),
        turn_detection="server_vad",
    )


@pytest.mark.asyncio
async def test_server_vad_stream_only_appends_audio_until_upstream_detects_turn(
    tmp_path: Path,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)

    await gateway.append_audio(session, b"\x01\x00" * 1600)
    await gateway.append_audio(session, b"\x02\x00" * 1600)

    assert session.client.appended == [
        b"\x01\x00" * 1600,
        b"\x02\x00" * 1600,
    ]
    session.client.commit_audio.assert_not_awaited()
    session.client.create_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_server_vad_speech_events_segment_patient_audio_and_interrupt_response(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    websocket = FakeWebSocket()
    session.connected_clients.add(websocket)
    session.responding = True
    session.current_response_id = "resp_old"
    session.input_pre_roll.extend(b"\x01\x00" * 800)
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )
    monkeypatch.setattr(
        voice_gateway_module.ScheduleTaskStore,
        "get_guidance",
        lambda _self, _session_no: None,
    )

    await gateway._handle_event(
        session,
        {"type": "input_audio_buffer.speech_started"},
    )
    await gateway.append_audio(session, b"\x02\x00" * 1600)
    await gateway._handle_event(
        session,
        {"type": "input_audio_buffer.speech_stopped"},
    )

    assert session.client.cancel_response.await_count == 1
    assert session.client.commit_audio.await_count == 0
    assert session.client.create_response.await_count == 0
    assert session.input_audio_url is not None
    assert any(
        isinstance(event, PatientAudioEvent)
        and event.message_id == "MSG-PATIENT-VOICE-2"
        for event in session.publisher.events
    )
    assert {"type": "speech_started"} in websocket.messages
    assert {"type": "speech_stopped"} in websocket.messages


@pytest.mark.asyncio
async def test_server_vad_transcript_dispatches_schedule_and_extraction_without_response_create(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.input_turn_no = 2
    session.input_message_id = "MSG-PATIENT-VOICE-2"
    session.input_audio_url = "/audio/patient.wav"
    saved_messages: list[dict] = []
    dispatch = Mock()

    class FakeHistory:
        async def save_message(self, _session_no: str, **kwargs):
            saved_messages.append(kwargs)
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr(voice_gateway_module, "DialogHistoryManager", FakeHistory)
    monkeypatch.setattr(
        voice_gateway_module,
        "dispatch_voice_answer_workers",
        dispatch,
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "get_keyword_matcher",
        lambda: SimpleNamespace(match=lambda _text: []),
    )

    await gateway._handle_event(
        session,
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "我有一点头晕",
        },
    )

    assert saved_messages[0]["content_text"] == "我有一点头晕"
    assert saved_messages[0]["audio_url"] == "/audio/patient.wav"
    assert any(isinstance(event, PatientAnswerEvent) for event in session.publisher.events)
    dispatch.assert_called_once()
    session.client.commit_audio.assert_not_awaited()
    session.client.create_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_function_call_uses_official_output_then_response_create(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.current_response_id = "resp_tool"
    session.current_generation = VoiceGeneration(
        generation_id="GEN-TOOL",
        message_id="MSG-AI-TOOL",
        turn_no=3,
        response_id="resp_tool",
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "execute_tool",
        AsyncMock(return_value={"success": True, "message": "护士已收到呼叫"}),
    )
    publish_result = Mock()
    monkeypatch.setattr(
        voice_gateway_module,
        "publish_tool_result",
        publish_result,
    )

    await gateway._handle_event(
        session,
        {
            "type": "response.function_call_arguments.done",
            "response_id": "resp_tool",
            "call_id": "call_001",
            "name": "request_nurse_assistance",
            "arguments": (
                '{"requested_action":"measure_blood_pressure",'
                '"reason":"头晕","urgency":"urgent"}'
            ),
        },
    )

    session.client.send_tool_result.assert_awaited_once_with(
        "call_001",
        {"success": True, "message": "护士已收到呼叫"},
    )
    session.client.create_response.assert_awaited_once()
    publish_result.assert_called_once()
    assert any(isinstance(event, ToolCallEvent) for event in session.publisher.events)


@pytest.mark.asyncio
async def test_response_ids_keep_mixed_tool_response_until_each_response_finishes(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    saved_messages: list[dict] = []
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )

    class FakeHistory:
        async def save_message(self, _session_no: str, **kwargs):
            saved_messages.append(kwargs)
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr(voice_gateway_module, "DialogHistoryManager", FakeHistory)
    monkeypatch.setattr(
        voice_gateway_module,
        "execute_tool",
        AsyncMock(return_value={"success": True}),
    )
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_1"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.audio_transcript.delta",
            "response_id": "resp_1",
            "delta": "先为您呼叫护士。",
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.function_call_arguments.done",
            "response_id": "resp_1",
            "call_id": "call_1",
            "name": "request_nurse_assistance",
            "arguments": '{"requested_action":"other","reason":"需要协助"}',
        },
    )
    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_2"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_1", "status": "completed"},
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.audio_transcript.delta",
            "response_id": "resp_2",
            "delta": "护士已经收到消息。",
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_2", "status": "completed"},
        },
    )

    assert [message["content_text"] for message in saved_messages] == [
        "先为您呼叫护士。",
        "护士已经收到消息。",
    ]
    completed_events = [
        event
        for event in session.publisher.events
        if isinstance(event, DialogMessageEvent)
    ]
    assert len(completed_events) == 2
    assert not any(
        isinstance(event, DialogMessageEvent) and not event.content
        for event in session.publisher.events
    )


@pytest.mark.asyncio
async def test_cancelled_response_residual_audio_is_not_recreated_as_new_message(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_old"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "input_audio_buffer.speech_started",
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_old", "status": "cancelled"},
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.audio.delta",
            "response_id": "resp_old",
            "delta": "AQACAA==",
        },
    )

    assert session.current_generation is None
    assert not session.publisher.events
