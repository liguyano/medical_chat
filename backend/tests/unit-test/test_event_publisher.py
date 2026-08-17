"""测试事件发布器
作用：验证DialogEventPublisher的发布功能
"""
import sys
import os

# UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from datetime import datetime
from app.schemas.events import (
    DialogTurnEvent,
    DialogTextEvent,
    ToolCallEvent,
    SessionStartEvent,
    EventType,
)
from app.workers.event_publisher import DialogEventPublisher, StreamKeyHelper
from app.utils.redis_client import init_redis, get_redis


@pytest.fixture(scope="module")
def redis_setup():
    """初始化Redis客户端"""
    init_redis(host="localhost", port=6379, db=0)
    yield
    # 清理测试数据
    redis = get_redis()
    keys = redis.client.keys(b"dialog_stream:test_*")
    if keys:
        redis.client.delete(*keys)


def test_publish_dialog_turn_event(redis_setup):
    """测试发布对话轮次事件"""
    session_id = "test_session_001"
    publisher = DialogEventPublisher(session_id)

    # 创建事件
    event = DialogTurnEvent(
        session_id=session_id,
        turn_number=1,
        question="您的年龄是多少?",
        answer="我今年65岁。",
        tool_calls=None,
        metadata={"source": "patient"}
    )

    # 发布事件
    message_id = publisher.publish(event)
    assert message_id is not None, "事件发布失败"

    # 验证：从Stream读取消息
    redis = get_redis()
    messages = redis.xread(
        streams={publisher.stream_key: "0"},
        count=1
    )

    assert len(messages) == 1, "未读取到消息"
    stream_key, message_list = messages[0]
    assert stream_key.decode('utf-8') == publisher.stream_key

    message_id_bytes, fields = message_list[0]
    assert fields[b'event_type'].decode('utf-8') == EventType.DIALOG_TURN
    assert fields[b'question'].decode('utf-8') == "您的年龄是多少?"
    assert fields[b'answer'].decode('utf-8') == "我今年65岁。"

    print(f"✅ 对话轮次事件发布成功: {message_id}")


def test_publish_dialog_text_event(redis_setup):
    """测试发布文本输出事件"""
    session_id = "test_session_002"
    publisher = DialogEventPublisher(session_id)

    event = DialogTextEvent(
        session_id=session_id,
        turn_number=1,
        text_chunk="您好，我是",
        is_final=False
    )

    message_id = publisher.publish(event)
    assert message_id is not None

    print(f"✅ 文本输出事件发布成功: {message_id}")


def test_publish_tool_call_event(redis_setup):
    """测试发布工具调用事件"""
    session_id = "test_session_003"
    publisher = DialogEventPublisher(session_id)

    event = ToolCallEvent(
        session_id=session_id,
        turn_number=2,
        tool_name="get_education_material",
        tool_args={"category": "tobacco", "level": "high"},
        tool_result={"material_id": "edu_001", "content": "戒烟宣教材料..."}
    )

    message_id = publisher.publish(event)
    assert message_id is not None

    print(f"✅ 工具调用事件发布成功: {message_id}")


def test_publish_batch_events(redis_setup):
    """测试批量发布事件"""
    session_id = "test_session_004"
    publisher = DialogEventPublisher(session_id)

    events = [
        SessionStartEvent(
            session_id=session_id,
            patient_id="P001",
            task_id="T001",
            form_ids=["FORM_001", "FORM_002"]
        ),
        DialogTurnEvent(
            session_id=session_id,
            turn_number=1,
            question="问题1",
            answer="回答1"
        ),
        DialogTurnEvent(
            session_id=session_id,
            turn_number=2,
            question="问题2",
            answer="回答2"
        ),
    ]

    message_ids = publisher.publish_batch(events)
    assert len(message_ids) == 3
    assert all(mid is not None for mid in message_ids)

    # 验证：读取所有消息
    redis = get_redis()
    messages = redis.xread(
        streams={publisher.stream_key: "0"},
        count=10
    )

    stream_key, message_list = messages[0]
    assert len(message_list) == 3

    print(f"✅ 批量发布事件成功: {len(message_ids)}条")


def test_stream_key_helper():
    """测试Stream键名辅助类"""
    assert StreamKeyHelper.dialog_stream("session_001") == "dialog_stream:session_001"
    assert StreamKeyHelper.schedule_stream("task_001") == "schedule_stream:task_001"
    assert StreamKeyHelper.extraction_stream("session_002") == "extraction_stream:session_002"

    print("✅ StreamKeyHelper测试通过")


def test_event_serialization(redis_setup):
    """测试事件序列化正确性"""
    session_id = "test_session_005"
    publisher = DialogEventPublisher(session_id)

    # 创建包含复杂字段的事件
    event = DialogTurnEvent(
        session_id=session_id,
        turn_number=1,
        question="测试问题",
        answer="测试回答",
        tool_calls=[
            {"name": "tool1", "args": {"arg1": "value1"}},
            {"name": "tool2", "args": {"arg2": "value2"}},
        ],
        metadata={"nested": {"key": "value"}}
    )

    message_id = publisher.publish(event)
    assert message_id is not None

    # 读取并验证序列化
    redis = get_redis()
    messages = redis.xread(
        streams={publisher.stream_key: "0"},
        count=1
    )

    message_id_bytes, fields = messages[0][1][0]
    tool_calls_str = fields[b'tool_calls'].decode('utf-8')
    metadata_str = fields[b'metadata'].decode('utf-8')

    import json
    tool_calls = json.loads(tool_calls_str)
    metadata = json.loads(metadata_str)

    assert len(tool_calls) == 2
    assert tool_calls[0]["name"] == "tool1"
    assert metadata["nested"]["key"] == "value"

    print("✅ 事件序列化测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
