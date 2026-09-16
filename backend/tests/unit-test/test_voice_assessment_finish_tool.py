from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.voice_gateway as voice_gateway_module
from app.services.dialog_audio_store import DialogAudioStore
from app.services.voice_gateway import VoiceGateway, VoiceSession


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        return True


class FakePublisher:
    def __init__(self) -> None:
        self.events: list = []

    def publish(self, event):
        self.events.append(event)
        return f"{len(self.events)}-0"


class FakeClient:
    def __init__(self) -> None:
        self.create_response = AsyncMock()
        self.cancel_response = AsyncMock()
        self.update_instructions = AsyncMock()
        self.send_tool_result = AsyncMock()
        self.instructions = "基础提示词"


class FakeRealtimeClientForConnect:
    instances = []

    def __init__(self, **_kwargs):
        async def connect_impl(**kwargs):
            self.instructions = kwargs["instructions"]

        self.connect = AsyncMock(side_effect=connect_impl)
        self.create_response = AsyncMock()
        self.cancel_response = AsyncMock()
        self.update_instructions = AsyncMock()
        self.send_tool_result = AsyncMock()
        self.instructions = ""
        self.__class__.instances.append(self)

    async def append_audio(self, _data: bytes) -> None:
        return None


def make_session(tmp_path: Path) -> VoiceSession:
    return VoiceSession(
        session_no="SESS-FINISH-TOOL",
        task_id=1,
        patient_id=2,
        patient_info={"name": "患者", "gender": "男", "age": 60},
        scale_codes=["scale"],
        instructions="基础提示词",
        client=FakeClient(),
        redis=FakeRedis(),
        audio_store=DialogAudioStore(tmp_path),
        publisher=FakePublisher(),
        turn_detection="server_vad",
    )


def question(question_id: int, text: str):
    return SimpleNamespace(
        question_id=question_id,
        question_code=f"Q{question_id}",
        question_name=text,
        patient_text=text,
        question_type="单选",
        required=True,
        sort_no=question_id,
        options=[],
    )


@pytest.mark.asyncio
async def test_voice_connection_exposes_finish_check_tool_and_requires_it_before_exit(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    q1 = question(1, "最近一个月，您使用电话通常能做到什么程度？")
    progress = SimpleNamespace(
        current=0,
        total=1,
        completed=False,
        remaining_question_ids=(1,),
    )
    voice_config = SimpleNamespace(
        websocket_url="wss://example.invalid/realtime",
        model="qwen-test",
        voice="longanqian",
        timeout=30,
        model_extra={"provider": "qwen_audio_realtime", "turn_detection": "server_vad"},
        resolved_api_key=lambda: "test-key",
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "get_app_config",
        lambda: SimpleNamespace(get_agent_model_config=lambda *_args, **_kwargs: voice_config),
    )
    monkeypatch.setattr(voice_gateway_module, "get_redis", lambda: FakeRedis())
    monkeypatch.setattr(
        voice_gateway_module,
        "ScheduleTaskStore",
        lambda _redis: SimpleNamespace(
            get_plan=lambda _session_no: SimpleNamespace(tasks=[q1])
        ),
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "filter_manual_tasks",
        lambda tasks: list(tasks),
    )
    FakeRealtimeClientForConnect.instances = []
    monkeypatch.setattr(
        voice_gateway_module,
        "QwenRealtimeClient",
        FakeRealtimeClientForConnect,
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "DialogEventPublisher",
        lambda _session_no: FakePublisher(),
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "DialogAudioStore",
        lambda: DialogAudioStore(tmp_path),
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "build_recovery_decision",
        lambda _session_no, _tasks: SimpleNamespace(
            progress=progress,
            next_question=q1,
            should_recover=True,
        ),
    )

    async def consume_stub(_session):
        return None

    monkeypatch.setattr(gateway, "_consume_upstream", consume_stub)

    await gateway.get_or_create(
        session_no="SESS-FINISH-CONNECT",
        task_id=1,
        patient_id=2,
        patient_info={"name": "患者", "gender": "男", "age": 60},
        scale_codes=["scale"],
    )

    client = FakeRealtimeClientForConnect.instances[-1]
    connect_kwargs = client.connect.await_args.kwargs
    tool_names = [
        item.get("function", {}).get("name")
        for item in connect_kwargs["tools"]
    ]
    assert "request_assessment_finish" in tool_names
    assert "request_assessment_finish" in connect_kwargs["instructions"]
    assert "不得直接宣布评估完成" in connect_kwargs["instructions"]


@pytest.mark.asyncio
async def test_finish_check_tool_routes_incomplete_progress_into_existing_recovery(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    next_question = question(13, "最近一个月，您使用电话通常能做到什么程度？")
    session.task_list = [next_question]
    execute = AsyncMock(return_value={"success": True, "completed": True})
    monkeypatch.setattr(voice_gateway_module, "execute_tool", execute)
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "latest_patient_message_no",
        lambda _session_no: "MSG-PATIENT-VOICE-2",
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "extraction_processed",
        lambda _redis, _session_no, _message_no: True,
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "build_recovery_decision",
        lambda _session_no, _tasks: SimpleNamespace(
            should_recover=True,
            next_question=next_question,
            progress=SimpleNamespace(
                current=12,
                total=13,
                completed=False,
                remaining_question_ids=(13,),
            ),
        ),
    )

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_finish"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.function_call_arguments.done",
            "response_id": "resp_finish",
            "call_id": "call_finish",
            "name": "request_assessment_finish",
            "arguments": "{}",
        },
    )

    execute.assert_not_awaited()
    tool_result = session.client.send_tool_result.await_args.args[1]
    assert tool_result["completed"] is False
    assert tool_result["current"] == 12
    assert tool_result["total"] == 13
    assert tool_result["next_question"] == next_question.patient_text
    recovery_prompt = session.client.update_instructions.await_args.args[0]
    assert next_question.patient_text in recovery_prompt
    assert "当前唯一允许询问的问题" in recovery_prompt
    assert session.recovery_mode_active is True
    assert session.recovery_current_question_id == 13
    assert session.next_response_is_recovery is True
    session.client.create_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_finish_check_tool_allows_exit_only_when_progress_is_complete(
    tmp_path: Path,
    monkeypatch,
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    execute = AsyncMock(return_value={"success": False})
    monkeypatch.setattr(voice_gateway_module, "execute_tool", execute)
    monkeypatch.setattr(voice_gateway_module, "publish_tool_result", Mock())
    monkeypatch.setattr(
        gateway,
        "_next_patient_message",
        lambda _session_no: (2, "MSG-PATIENT-VOICE-2"),
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "latest_patient_message_no",
        lambda _session_no: "MSG-PATIENT-VOICE-2",
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "extraction_processed",
        lambda _redis, _session_no, _message_no: True,
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "build_recovery_decision",
        lambda _session_no, _tasks: SimpleNamespace(
            should_recover=False,
            next_question=None,
            progress=SimpleNamespace(
                current=13,
                total=13,
                completed=True,
                remaining_question_ids=(),
            ),
        ),
    )

    await gateway._handle_event(
        session,
        {"type": "response.created", "response": {"id": "resp_finish"}},
    )
    await gateway._handle_event(
        session,
        {
            "type": "response.function_call_arguments.done",
            "response_id": "resp_finish",
            "call_id": "call_finish",
            "name": "request_assessment_finish",
            "arguments": "{}",
        },
    )

    execute.assert_not_awaited()
    tool_result = session.client.send_tool_result.await_args.args[1]
    assert tool_result == {
        "success": True,
        "completed": True,
        "current": 13,
        "total": 13,
        "remaining_count": 0,
        "message": "结构化评估已确认完成，可以向患者礼貌结束本次评估。",
    }
    assert session.recovery_mode_active is False
    session.client.update_instructions.assert_not_awaited()
