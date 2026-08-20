"""SSE 断线续读 ID 与语音事件格式测试。"""

import json

from app.services.sse_service import _max_stream_id, format_sse_event


def test_snapshot_event_id_does_not_break_redis_stream_read():
    """快照事件 ID 不是 Redis Stream ID 时应回退到有效流 ID。"""
    assert _max_stream_id("snapshot:GEN-1", "1787130319211-0") == "1787130319211-0"
    assert _max_stream_id("1787130319211-0", "snapshot:GEN-1") == "1787130319211-0"


def test_audio_index_sse_payload_keeps_turn_number_and_playback_metadata():
    event = format_sse_event(
        "1710000000000-0",
        {
            b"event_type": b"dialog_audio",
            b"task_id": b"1",
            b"session_id": b"SESS-1",
            b"message_id": b"MSG-AI-1",
            b"timestamp": b"2026-08-20T10:00:00Z",
            b"turn_number": b"3",
            b"audio_url": b"/api/dialog/SESS-1/audio/GEN-1/assistant.wav",
            b"audio_format": b"wav",
            b"role": b"assistant",
            b"sample_rate": b"24000",
            b"is_final": b"1",
        },
    )
    payload = json.loads(event["data"])["payload"]
    assert payload["turn_no"] == 3
    assert payload["audio_format"] == "wav"
    assert payload["sample_rate"] == 24000
    assert payload["is_final"] is True
