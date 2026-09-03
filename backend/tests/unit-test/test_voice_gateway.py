from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

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
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.locks: dict[str, str] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    def exists(self, key: str) -> int:
        return int(key in self.values)

    def acquire_lock(self, key: str, token: str, ttl: int = 30) -> bool:
        if key in self.locks:
            return False
        self.locks[key] = token
        return True

    def release_lock(self, key: str, token: str) -> bool:
        if self.locks.get(key) != token:
            return False
        del self.locks[key]
        return True


def make_session(tmp_path: Path) -> VoiceSession:
    return VoiceSession(
        session_no="SESS-VOICE",
        task_id=1,
        patient_id=2,
        patient_info={"name": "患者"},
        scale_codes=["scale"],
        task_list=[],
        instructions="基础提示词",
        client=FakeClient(),
        redis=FakeRedis(),
        audio_store=DialogAudioStore(tmp_path),
        publisher=FakePublisher(),
        turn_detection="server_vad",
    )


@pytest.mark.asyncio
async def test_question_choice_missing_blocks_voice_text_and_audio(tmp_path):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [], "active_question_id": None}
    )
    session.question_source_message_no = "patient-1"
    gateway._next_patient_message = lambda _: (1, "patient-1")
    await gateway._start_generation(session, response_id="response-1")
    await gateway._handle_text_delta(session, "重复的问句", source="text", response_id="response-1")
    await gateway._handle_audio_delta(session, b"\x00\x00", response_id="response-1")
    assert session.publisher.events == []
    assert not session.current_generation.all_audio
    assert not session.current_generation.text


@pytest.mark.asyncio
async def test_voice_generation_keeps_choice_of_its_own_patient_turn(tmp_path):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    first = QuestionTurnSelection({"candidate_question_ids": [1]})
    session.question_turn = first
    session.question_source_message_no = "patient-1"
    gateway._next_patient_message = lambda _: (1, "patient-1")
    await gateway._start_generation(session, response_id="old")
    session.question_turn = QuestionTurnSelection({"candidate_question_ids": [2]})
    session.question_source_message_no = "patient-2"
    generation = session.generations["old"]
    assert generation.question_turn is first
    assert generation.source_message_no == "patient-1"


@pytest.mark.asyncio
async def test_invalid_choice_then_blocked_text_still_runs_tool_correction(tmp_path, monkeypatch):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [1], "active_question_id": None}
    )
    gateway._next_patient_message = lambda _: (1, "patient-1")
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    await gateway._handle_event(session, {"type": "response.created", "response": {"id": "r1"}})
    await gateway._handle_tool_call(
        session,
        call_id="c1",
        name="report_question_choice",
        arguments={"selected_question_id": 99, "active_question_id": 99},
        response_id="r1",
    )
    await gateway._handle_text_delta(session, "未经允许的问题", source="text", response_id="r1")
    await gateway._handle_event(session, {"type": "response.done", "response": {"id": "r1"}})
    assert not any(isinstance(event, DialogMessageEvent) for event in session.publisher.events)
    session.client.create_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_changed_choice_after_visible_text_does_not_kill_voice_consumer(
    tmp_path, monkeypatch
):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [1, 2], "active_question_id": None}
    )
    gateway._next_patient_message = lambda _: (1, "patient-1")
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    await gateway._handle_event(session, {"type": "response.created", "response": {"id": "r1"}})
    await gateway._handle_tool_call(
        session,
        call_id="c1",
        name="report_question_choice",
        arguments={"selected_question_id": 1, "active_question_id": 1},
        response_id="r1",
    )
    await gateway._handle_text_delta(session, "问题一", source="text", response_id="r1")
    await gateway._handle_tool_call(
        session,
        call_id="c2",
        name="report_question_choice",
        arguments={"selected_question_id": 2, "active_question_id": 2},
        response_id="r1",
    )
    await gateway._handle_event(session, {"type": "response.done", "response": {"id": "r1"}})
    assert not session.generations
    assert not any(isinstance(event, DialogMessageEvent) for event in session.publisher.events)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "incomplete", "cancelled"])
async def test_unsuccessful_voice_response_does_not_record_question(tmp_path, monkeypatch, status):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [1], "active_question_id": None}
    )
    session.question_turn.report({"selected_question_id": 1, "active_question_id": 1})
    gateway._next_patient_message = lambda _: (1, "patient-1")
    save = AsyncMock()
    monkeypatch.setattr(
        voice_gateway_module, "DialogHistoryManager", lambda: SimpleNamespace(save_message=save)
    )
    await gateway._handle_event(session, {"type": "response.created", "response": {"id": "r1"}})
    await gateway._handle_text_delta(session, "部分问题", source="text", response_id="r1")
    await gateway._handle_event(
        session, {"type": "response.done", "response": {"id": "r1", "status": status}}
    )
    save.assert_not_awaited()
    assert not session.generations


@pytest.mark.asyncio
@pytest.mark.parametrize("selected,active", [(1, 1), (None, 2), (None, None)])
async def test_voice_choice_records_only_after_visible_response_completed(
    tmp_path, monkeypatch, selected, active
):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.question_source_message_no = "patient-stable"
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [1], "active_question_id": 2}
    )
    gateway._next_patient_message = lambda _: (1, "patient-stable")
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    save = AsyncMock()
    monkeypatch.setattr(
        voice_gateway_module, "DialogHistoryManager", lambda: SimpleNamespace(save_message=save)
    )
    monkeypatch.setattr(voice_gateway_module.model_base, "SessionLocal", MagicMock())
    record = Mock()
    monkeypatch.setattr("app.services.dialog_question_service.record_question_turn", record)
    monkeypatch.setattr(
        "app.services.voice_completion_service.mark_voice_response_completed",
        Mock(return_value=False),
    )

    await gateway._handle_event(session, {"type": "response.created", "response": {"id": "choice"}})
    await gateway._handle_tool_call(
        session,
        call_id="c1",
        name="report_question_choice",
        arguments={"selected_question_id": selected, "active_question_id": active},
        response_id="choice",
    )
    await gateway._handle_event(
        session, {"type": "response.done", "response": {"id": "choice", "status": "completed"}}
    )
    record.assert_not_called()
    save.assert_not_awaited()

    await gateway._handle_event(
        session, {"type": "response.created", "response": {"id": "visible"}}
    )
    await gateway._handle_text_delta(session, "自然回复", source="text", response_id="visible")
    await gateway._handle_event(
        session, {"type": "response.done", "response": {"id": "visible", "status": "completed"}}
    )
    await gateway._handle_event(
        session, {"type": "response.done", "response": {"id": "visible", "status": "completed"}}
    )
    save.assert_awaited_once()
    assert save.await_args.kwargs["related_question_id"] == active
    assert save.await_args.kwargs["intent_type"] == (
        "提问" if selected else "澄清" if active else "回应"
    )
    record.assert_called_once()
    assert record.call_args.args[3:] == ("patient-stable", selected, active)
    messages = [
        event for event in session.publisher.events if isinstance(event, DialogMessageEvent)
    ]
    assert len(messages) == 1
    assert messages[0].question_id == (str(active) if active else None)


@pytest.mark.asyncio
async def test_cancelled_choice_tool_cannot_start_or_authorize_continuation(tmp_path, monkeypatch):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.question_source_message_no = "patient-1"
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [1], "active_question_id": None}
    )
    gateway._next_patient_message = lambda _: (1, "patient-1")
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    await gateway._handle_event(session, {"type": "response.created", "response": {"id": "r1"}})
    await gateway._handle_tool_call(
        session,
        call_id="c1",
        name="report_question_choice",
        arguments={"selected_question_id": 1, "active_question_id": 1},
        response_id="r1",
    )
    await gateway._handle_event(
        session, {"type": "response.done", "response": {"id": "r1", "status": "cancelled"}}
    )
    session.client.create_response.assert_not_awaited()
    assert not session.question_turn.allow_output


@pytest.mark.asyncio
async def test_suppressed_response_late_text_is_not_shown(tmp_path):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    gateway._next_patient_message = lambda _: (1, "patient-1")
    await gateway._handle_event(session, {"type": "response.created", "response": {"id": "r1"}})
    session.suppressed_response_ids.add("r1")
    await gateway._handle_text_delta(session, "旧响应迟到文本", source="text", response_id="r1")
    assert session.publisher.events == []


@pytest.mark.asyncio
async def test_late_choice_for_removed_response_cannot_select_new_turn(tmp_path, monkeypatch):
    from app.services.dialog_question_turn import QuestionTurnSelection

    gateway = VoiceGateway()
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    session = make_session(tmp_path)
    session.question_turn = QuestionTurnSelection(
        {"candidate_question_ids": [1], "active_question_id": None}
    )
    await gateway._handle_tool_call(
        session,
        call_id="old-call",
        name="report_question_choice",
        arguments={"selected_question_id": 1, "active_question_id": 1},
        response_id="removed-old-response",
    )
    assert not session.question_turn.allow_output
    session.client.create_response.assert_not_awaited()


def make_question(question_id: int, code: str, name: str) -> QuestionTask:
    return QuestionTask(
        question_id=question_id,
        question_code=code,
        question_name=name,
        patient_text=f"请问您的{name}情况如何？",
        question_type="text",
        required=True,
        sort_no=question_id,
    )


def test_resume_context_removes_recorded_questions_and_keeps_answer_summary():
    questions = [
        make_question(1, "weakness", "虚弱/乏力"),
        make_question(2, "vision", "视力情况"),
    ]

    instructions, remaining = VoiceGateway._build_resume_context(
        patient_info={"name": "患者"},
        task_list=questions,
        recorded_answers=[
            {
                "question_id": 1,
                "question_code": "weakness",
                "question_text": "虚弱/乏力",
                "display_value": "无",
            }
        ],
    )

    assert [question.question_id for question in remaining] == [2]
    assert "虚弱/乏力" in instructions
    assert "无" in instructions
    assert "不得重复询问" in instructions
    assert "[vision]" in instructions


def test_resume_context_for_completed_plan_forbids_restarting_scale():
    question = make_question(1, "weakness", "虚弱/乏力")

    instructions, remaining = VoiceGateway._build_resume_context(
        patient_info={"name": "患者"},
        task_list=[question],
        recorded_answers=[
            {
                "question_id": 1,
                "question_code": "weakness",
                "question_text": "虚弱/乏力",
                "display_value": "无",
            }
        ],
    )

    assert remaining == []
    assert "全部必填题均已有有效记录" in instructions
    assert "禁止重新开始量表" in instructions


@pytest.mark.asyncio
async def test_refresh_guidance_reloads_recorded_answers_before_next_speech(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.task_list = [
        make_question(1, "weakness", "虚弱/乏力"),
        make_question(2, "vision", "视力情况"),
    ]
    monkeypatch.setattr(
        gateway,
        "_load_question_context",
        lambda _session_no, _source=None: {
            "candidate_question_ids": [2],
            "active_question_id": None,
            "questions": [{"question_id": 2, "question_text": "视力情况", "status": "unasked"}],
            "recorded_answers": [
                {
                    "question_id": 1,
                    "question_code": "weakness",
                    "question_text": "虚弱/乏力",
                    "display_value": "无",
                }
            ],
        },
    )
    monkeypatch.setattr(
        voice_gateway_module.ScheduleTaskStore,
        "get_guidance",
        lambda _self, _session_no: {"constraint_prompt": "下一题询问视力"},
    )

    await gateway._refresh_schedule_guidance(session)

    updated = session.client.update_instructions.await_args.args[0]
    assert "[vision]" in updated
    assert "虚弱/乏力" in updated
    assert "下一题询问视力" in updated
    assert session.instructions in updated


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
        isinstance(event, PatientAudioEvent) and event.message_id == "MSG-PATIENT-VOICE-2"
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
                '{"requested_action":"measure_blood_pressure","reason":"头晕","urgency":"urgent"}'
            ),
        },
    )

    session.client.send_tool_result.assert_awaited_once_with(
        "call_001",
        {"success": True, "message": "护士已收到呼叫"},
    )
    session.client.create_response.assert_awaited_once()
    publish_result.assert_called_once()
    assert publish_result.call_args.kwargs["source_invocation_id"] == "call_001"
    assert any(isinstance(event, ToolCallEvent) for event in session.publisher.events)


@pytest.mark.asyncio
async def test_function_call_waits_for_active_response_before_creating_continuation(
    tmp_path: Path,
    monkeypatch,
):
    """工具调用发生在当前响应中时，必须等 response.done 后再创建下一响应。"""
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "execute_tool",
        AsyncMock(return_value={"success": True, "message": "宣教已展示"}),
    )
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_education"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.function_call_arguments.done",
            "response_id": "resp_education",
            "call_id": "call_education",
            "name": "get_education_material",
            "arguments": '{"category":"tobacco","level":2}',
        },
    )

    session.client.create_response.assert_not_awaited()
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_education", "status": "completed"},
        },
    )

    session.client.create_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_function_call_is_ignored(tmp_path: Path, monkeypatch):
    """上游重复投递同一 call_id 时不得重复执行宣教或呼叫护士。"""
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    execute = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(voice_gateway_module, "execute_tool", execute)
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    event = {
        "type": "response.function_call_arguments.done",
        "response_id": "resp_tool",
        "call_id": "call_duplicate",
        "name": "get_education_material",
        "arguments": '{"category":"tobacco","level":2}',
    }

    await gateway._handle_event(session, event)
    await gateway._handle_event(session, event)

    execute.assert_awaited_once()
    session.client.send_tool_result.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_active_response_race_recovers_without_text_fallback(
    tmp_path: Path,
):
    """Qwen 无活动响应竞态只清理本地状态，不把语音会话降级卡死。"""
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    websocket = FakeWebSocket()
    session.connected_clients.add(websocket)
    session.pending_tool_responses = 1

    await gateway._handle_event(
        session,
        {
            "type": "error",
            "error": {
                "code": "invalid_request_error",
                "message": "Conversation has no active response.",
            },
        },
    )

    session.client.create_response.assert_awaited_once()
    assert {"type": "state", "state": "listening"} in websocket.messages
    assert not session.publisher.events


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
    completed_response = Mock(return_value=False)
    monkeypatch.setattr(
        "app.services.voice_completion_service.mark_voice_response_completed",
        completed_response,
    )

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
        event for event in session.publisher.events if isinstance(event, DialogMessageEvent)
    ]
    assert len(completed_events) == 2
    completed_response.assert_called_once()
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


@pytest.mark.asyncio
async def test_function_call_intermediate_response_done_does_not_finish_assessment(
    tmp_path: Path,
    monkeypatch,
):
    """Function Calling 中间响应完成时必须等待工具后的最终语音回复。"""
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )

    class FakeHistory:
        async def save_message(self, _session_no: str, **kwargs):
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr(voice_gateway_module, "DialogHistoryManager", FakeHistory)
    monkeypatch.setattr(
        voice_gateway_module,
        "execute_tool",
        AsyncMock(return_value={"success": True}),
    )
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    completed_response = Mock(return_value=False)
    monkeypatch.setattr(
        "app.services.voice_completion_service.mark_voice_response_completed",
        completed_response,
    )

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_tool"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.function_call_arguments.done",
            "response_id": "resp_tool",
            "call_id": "call-1",
            "name": "request_nurse_assistance",
            "arguments": "{}",
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_tool", "status": "completed"},
        },
    )

    completed_response.assert_not_called()

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_final"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.audio_transcript.delta",
            "response_id": "resp_final",
            "delta": "护士已经收到您的请求。",
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_final", "status": "completed"},
        },
    )

    completed_response.assert_called_once()


@pytest.mark.asyncio
async def test_empty_response_done_does_not_finish_assessment(
    tmp_path: Path,
    monkeypatch,
):
    """没有患者可见文字或音频的 response.done 不得触发任务完成。"""
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )
    completed_response = Mock(return_value=False)
    monkeypatch.setattr(
        "app.services.voice_completion_service.mark_voice_response_completed",
        completed_response,
    )

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_empty"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_empty", "status": "completed"},
        },
    )

    completed_response.assert_not_called()
    assert session.current_generation is None


@pytest.mark.asyncio
async def test_visible_response_broadcasts_completion_marker_before_finalize(
    tmp_path: Path,
    monkeypatch,
):
    """最后音频入队后先向患者端发送响应完成标记，再触发任务完成协调。"""
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    websocket = FakeWebSocket()
    session.connected_clients.add(websocket)
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )

    class FakeHistory:
        async def save_message(self, _session_no: str, **kwargs):
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr(voice_gateway_module, "DialogHistoryManager", FakeHistory)
    finalized = Mock(return_value=False)
    monkeypatch.setattr(
        "app.services.voice_completion_service.mark_voice_response_completed",
        finalized,
    )

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_final"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.audio_transcript.delta",
            "response_id": "resp_final",
            "delta": "本次评估已经完成。",
        },
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.done",
            "response": {"id": "resp_final", "status": "completed"},
        },
    )

    marker_index = websocket.messages.index(
        {"type": "response_completed", "response_id": "resp_final"}
    )
    listening_index = websocket.messages.index({"type": "state", "state": "listening"})
    assert marker_index < listening_index
    finalized.assert_called_once()
