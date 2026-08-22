from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app.services.voice_gateway as voice_gateway_module
from app.services.dialog_audio_store import DialogAudioStore
from app.services.voice_gateway import VoiceGateway, VoiceSession


class FakeClient:
    def __init__(self) -> None:
        self.create_response = Mock()
        self.update_instructions = Mock()

    async def append_audio(self, _data: bytes) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    def delete(self, *keys: str) -> int:
        return sum(self.values.pop(key, None) is not None for key in keys)


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object):
        self.events.append(event)
        return str(len(self.events))


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def make_session(tmp_path: Path, redis: FakeRedis | None = None) -> VoiceSession:
    return VoiceSession(
        session_no="SESS-TRANSCRIPT",
        task_id=1,
        patient_id=2,
        patient_info={"name": "患者"},
        scale_codes=["scale"],
        instructions="基础提示词",
        client=FakeClient(),
        redis=redis or FakeRedis(),
        audio_store=DialogAudioStore(tmp_path),
        publisher=FakePublisher(),
        require_transcript_confirmation=True,
    )


@pytest.mark.asyncio
async def test_transcript_draft_is_not_persisted_or_dispatched_until_confirmed(
    tmp_path: Path, monkeypatch
):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.input_turn_no = 2
    session.input_message_id = "MSG-PATIENT-2"
    session.input_audio_url = "/audio/patient.wav"
    saved: list[dict] = []

    class FakeHistory:
        async def save_message(self, _session_no: str, **kwargs):
            saved.append(kwargs)
            return SimpleNamespace(**kwargs)

    dispatch = Mock()
    monkeypatch.setattr(voice_gateway_module, "DialogHistoryManager", FakeHistory)
    monkeypatch.setattr(voice_gateway_module, "dispatch_voice_answer_workers", dispatch)
    monkeypatch.setattr(
        voice_gateway_module,
        "get_keyword_matcher",
        lambda: SimpleNamespace(match=lambda _text: []),
    )

    await gateway._handle_patient_transcript(session, "我有一点头晕")

    assert session.pending_transcript_id
    assert saved == []
    dispatch.assert_not_called()
    transcript_id = session.pending_transcript_id

    await gateway.confirm_transcript(session, transcript_id)
    assert saved[0]["content_text"] == "我有一点头晕"
    assert saved[0]["audio_url"] == "/audio/patient.wav"
    dispatch.assert_called_once()

    await gateway.confirm_transcript(session, transcript_id)
    assert len(saved) == 1
    dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_retry_discards_draft_and_is_idempotent(tmp_path: Path):
    gateway = VoiceGateway()
    session = make_session(tmp_path)
    session.input_turn_no = 1
    session.input_message_id = "MSG-PATIENT-1"

    await gateway._handle_patient_transcript(session, "重新录音前的内容")
    transcript_id = session.pending_transcript_id

    await gateway.retry_transcript(session, transcript_id)
    assert session.pending_transcript_id is None
    assert session.redis.get(f"voice_transcript_draft:{session.session_no}:{transcript_id}") is None

    await gateway.retry_transcript(session, transcript_id)
    with pytest.raises(ValueError, match="不存在或已过期"):
        await gateway.confirm_transcript(session, transcript_id)


@pytest.mark.asyncio
async def test_attach_restores_pending_draft_from_redis(tmp_path: Path):
    gateway = VoiceGateway()
    redis = FakeRedis()
    first = make_session(tmp_path, redis)
    first.input_turn_no = 3
    first.input_message_id = "MSG-PATIENT-3"
    await gateway._handle_patient_transcript(first, "断线前的草稿")
    transcript_id = first.pending_transcript_id

    restored = make_session(tmp_path, redis)
    websocket = FakeWebSocket()
    await gateway.attach(restored, websocket)

    assert restored.pending_transcript_id == transcript_id
    assert any(
        message.get("type") == "transcript_ready"
        and message.get("text") == "断线前的草稿"
        for message in websocket.messages
    )
