"""SSE 断线续读 ID 兼容测试。"""

from app.services.sse_service import _max_stream_id


def test_snapshot_event_id_does_not_break_redis_stream_read():
    """快照事件 ID 不是 Redis Stream ID 时应回退到有效流 ID。"""
    assert _max_stream_id("snapshot:GEN-1", "1787130319211-0") == "1787130319211-0"
    assert _max_stream_id("1787130319211-0", "snapshot:GEN-1") == "1787130319211-0"
