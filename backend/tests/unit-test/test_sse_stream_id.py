"""SSE 断线续读 ID 与语音事件格式测试。"""

import json

from app.services.sse_service import _format_snapshot_event, _max_stream_id, format_sse_event


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


def test_sse_envelope_separates_domain_event_id_from_stream_cursor():
    """业务关联使用领域事件 ID，断线续读保留 Redis Stream ID。"""
    event = format_sse_event(
        "1787205471545-0",
        {
            b"event_id": b"EDU-EVENT-1",
            b"event_type": b"education_triggered",
            b"task_id": b"112",
            b"session_id": b"SESS-1",
            b"material_id": b"EDU-TOBACCO-V1-L2",
            b"category": b"tobacco",
            b"level": b"2",
            b"document_version": b"1.0",
            b"title": "戒烟宣教".encode(),
            b"original_content": "原文".encode(),
            b"patient_content": "通俗文本".encode(),
            b"spoken_content": "播报文本".encode(),
        },
    )
    envelope = json.loads(event["data"])

    assert event["id"] == "1787205471545-0"
    assert envelope["event_id"] == "EDU-EVENT-1"
    assert envelope["stream_id"] == "1787205471545-0"


def test_snapshot_event_carries_real_stream_cursor():
    """快照事件的业务 ID 与 Redis Stream 续读游标必须分离。"""
    event = _format_snapshot_event(
        {
            "status": "streaming",
            "generation_id": "GEN-1",
            "task_id": 1,
            "session_id": "SESS-1",
            "message_id": "MSG-1",
            "turn_number": 2,
            "question_id": "104",
            "content": "正在生成",
            "last_event_id": "1787205471545-0",
            "updated_at": "2026-09-04T10:30:00Z",
        }
    )
    assert event is not None
    envelope = json.loads(event["data"])

    assert event["id"] == "1787205471545-0"
    assert envelope["event_id"] == "snapshot:GEN-1"
    assert envelope["stream_id"] == "1787205471545-0"
