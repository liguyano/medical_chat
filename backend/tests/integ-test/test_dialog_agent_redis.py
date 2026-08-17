"""Dialog Agent 与真实 Redis Stream/状态适配器集成测试。"""

import json
from uuid import uuid4

import pytest
from medagent.agents.middleware import EventPublishMiddleware, ScheduleConstraintMiddleware

from app.managers.session_timeout_manager import SessionTimeoutManager
from app.schemas.events import ConstraintEvent, DialogTurnEvent, EventType
from app.utils.redis_client import RedisClient
from app.workers.dialog_agent_runtime import AppDialogEventSink, RedisConstraintSource
from app.workers.event_publisher import DialogEventPublisher


def _decode_stream(client: RedisClient, stream_key: str) -> list[dict[str, str]]:
    """读取并解码一个真实 Redis Stream。"""
    return [
        {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in fields.items()
        }
        for _, entries in client.xread({stream_key: "0"})
        for _, fields in entries
    ]


@pytest.fixture
def dialog_redis(monkeypatch):
    """提供真实 Redis，并只清理当前测试创建的唯一键。"""
    client = RedisClient(host="localhost", port=6379, db=0)
    if not client.ping():
        client.close()
        pytest.skip("Redis 测试环境不可用")

    import app.utils.redis_client as redis_module

    monkeypatch.setattr(redis_module, "redis_client", client)
    keys: list[str] = []
    try:
        yield client, keys
    finally:
        if keys:
            client.delete(*keys)
        client.close()


@pytest.mark.asyncio
async def test_constraint_event_is_consumed_once_with_persistent_cursor(dialog_redis):
    """Schedule 约束应由 Dialog 中间件消费一次并持久化游标。"""
    client, keys = dialog_redis
    session_id = f"dialog-redis-{uuid4().hex}"
    stream_key = f"dialog_stream:{session_id}"
    cursor_key = f"dialog_agent:constraint_cursor:{session_id}"
    keys.extend([stream_key, cursor_key])

    publisher = DialogEventPublisher(session_id)
    publisher.publish(
        DialogTurnEvent(
            session_id=session_id,
            turn_number=1,
            question="您好",
            answer="您好，请问您是否吸烟？",
        )
    )
    publisher.publish(
        ConstraintEvent(
            session_id=session_id,
            constraint_type="deviation",
            constraint_prompt="请回到吸烟史评估。",
            remaining_tasks=["smoking"],
        )
    )

    middleware = ScheduleConstraintMiddleware(RedisConstraintSource(client))
    first_context = {"session_id": session_id, "constraints": []}
    await middleware.before_agent(first_context)
    second_context = {"session_id": session_id, "constraints": []}
    await middleware.before_agent(second_context)

    assert first_context["constraints"] == ["请回到吸烟史评估。"]
    assert second_context["constraints"] == []
    assert client.get(cursor_key) != "0"
    assert 0 < client.ttl(cursor_key) <= 3600


@pytest.mark.asyncio
async def test_dialog_events_match_schedule_stream_contract(dialog_redis):
    """Dialog 中间件应向统一流发布可被 Schedule 消费的轮次和工具事件。"""
    client, keys = dialog_redis
    session_id = f"dialog-events-{uuid4().hex}"
    stream_key = f"dialog_stream:{session_id}"
    keys.append(stream_key)

    middleware = EventPublishMiddleware(
        session_id,
        AppDialogEventSink(session_id),
    )
    await middleware.after_agent(
        {
            "session_id": session_id,
            "turn_number": 5,
            "patient_input": "我每天抽十支烟。",
            "tool_calls": [
                {
                    "name": "get_education_material",
                    "arguments": {"category": "tobacco"},
                    "result": {"success": True},
                }
            ],
        },
        "了解，我会为您提供戒烟宣教。",
    )

    events = _decode_stream(client, stream_key)
    assert [event["event_type"] for event in events] == [
        EventType.DIALOG_TURN.value,
        EventType.TOOL_CALL.value,
    ]
    assert events[0]["turn_number"] == "5"
    assert events[0]["question"] == "我每天抽十支烟。"
    assert json.loads(events[0]["tool_calls"])[0]["name"] == "get_education_material"
    assert events[1]["tool_name"] == "get_education_material"
    assert json.loads(events[1]["tool_args"]) == {"category": "tobacco"}


def test_dialog_activity_timestamp_has_ttl_and_can_be_cleared(dialog_redis):
    """会话活动状态应设置 TTL，并能在会话结束时清理。"""
    client, keys = dialog_redis
    session_id = f"dialog-activity-{uuid4().hex}"
    activity_key = f"session_activity:{session_id}"
    keys.append(activity_key)
    manager = SessionTimeoutManager(timeout_minutes=1)

    assert manager.update_activity(session_id) is True
    assert manager.get_last_activity(session_id) is not None
    assert 0 < client.ttl(activity_key) <= 120
    assert manager.clear_activity(session_id) is True
    assert client.exists(activity_key) == 0
