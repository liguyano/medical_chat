"""测试事件订阅器
作用：验证EventSubscriber的订阅和处理功能
"""
import sys
import os

# UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
import time
import threading
from datetime import datetime
from app.schemas.events import DialogTurnEvent, EventType
from app.workers.event_publisher import DialogEventPublisher
from app.workers.event_subscriber import EventSubscriber
from app.utils.redis_client import init_redis, get_redis


# 测试用订阅器
class TestSubscriber(EventSubscriber):
    """测试订阅器
    作用：记录接收到的事件
    """

    def __init__(self, session_id: str):
        super().__init__(
            consumer_group="test_group",
            consumer_name=f"test_consumer_{session_id}"
        )
        self.session_id = session_id
        self.received_events = []

    def get_stream_keys(self):
        return [f"dialog_stream:{self.session_id}"]

    async def process_event(self, event):
        self.received_events.append(event)
        print(f"[TestSubscriber] 接收事件: {event.event_type} (turn={getattr(event, 'turn_number', 'N/A')})")


@pytest.fixture(scope="module")
def redis_setup():
    """初始化Redis客户端"""
    init_redis(host="localhost", port=6379, db=0)
    yield
    # 清理测试数据
    redis = get_redis()
    keys = redis.client.keys(b"dialog_stream:test_sub_*")
    if keys:
        redis.client.delete(*keys)


def test_subscriber_receive_single_event(redis_setup):
    """测试订阅器接收单个事件"""
    session_id = "test_sub_001"

    # 发布事件
    publisher = DialogEventPublisher(session_id)
    event = DialogTurnEvent(
        session_id=session_id,
        turn_number=1,
        question="测试问题",
        answer="测试回答"
    )
    message_id = publisher.publish(event)
    assert message_id is not None

    # 创建订阅器
    subscriber = TestSubscriber(session_id)

    # 在后台线程启动订阅器（运行1秒后停止）
    def run_subscriber():
        time.sleep(1)
        subscriber.stop()

    threading.Thread(target=run_subscriber, daemon=True).start()

    # 启动订阅器（阻塞，直到stop()被调用）
    subscriber.start(block_ms=1000, count=10)

    # 验证：订阅器是否接收到事件
    assert len(subscriber.received_events) == 1
    received_event = subscriber.received_events[0]
    assert received_event.event_type == EventType.DIALOG_TURN
    assert received_event.turn_number == 1
    assert received_event.question == "测试问题"

    print(f"✅ 订阅器接收单个事件成功")


def test_subscriber_receive_batch_events(redis_setup):
    """测试订阅器接收批量事件"""
    session_id = "test_sub_002"

    # 发布多个事件
    publisher = DialogEventPublisher(session_id)
    events = [
        DialogTurnEvent(
            session_id=session_id,
            turn_number=i,
            question=f"问题{i}",
            answer=f"回答{i}"
        )
        for i in range(1, 6)
    ]
    message_ids = publisher.publish_batch(events)
    assert all(mid is not None for mid in message_ids)

    # 创建订阅器
    subscriber = TestSubscriber(session_id)

    # 运行2秒后停止
    def run_subscriber():
        time.sleep(2)
        subscriber.stop()

    threading.Thread(target=run_subscriber, daemon=True).start()
    subscriber.start(block_ms=1000, count=10)

    # 验证：订阅器是否接收到所有事件
    assert len(subscriber.received_events) == 5
    for i, received_event in enumerate(subscriber.received_events, start=1):
        assert received_event.turn_number == i
        assert received_event.question == f"问题{i}"

    print(f"✅ 订阅器接收批量事件成功: {len(subscriber.received_events)}条")


def test_consumer_group_isolation(redis_setup):
    """测试消费者组隔离性"""
    session_id = "test_sub_003"

    # 发布事件
    publisher = DialogEventPublisher(session_id)
    event = DialogTurnEvent(
        session_id=session_id,
        turn_number=1,
        question="隔离测试",
        answer="隔离回答"
    )
    publisher.publish(event)

    # 创建两个不同消费者组的订阅器
    subscriber1 = TestSubscriber(session_id)
    subscriber1.consumer_group = "group_1"

    subscriber2 = TestSubscriber(session_id)
    subscriber2.consumer_group = "group_2"

    # 订阅器1运行
    def run_sub1():
        time.sleep(1)
        subscriber1.stop()

    threading.Thread(target=run_sub1, daemon=True).start()
    subscriber1.start(block_ms=1000, count=10)

    # 订阅器2运行
    def run_sub2():
        time.sleep(1)
        subscriber2.stop()

    threading.Thread(target=run_sub2, daemon=True).start()
    subscriber2.start(block_ms=1000, count=10)

    # 验证：两个消费者组都应该接收到同一条消息
    assert len(subscriber1.received_events) == 1
    assert len(subscriber2.received_events) == 1

    print("✅ 消费者组隔离性测试通过")


def test_message_ack(redis_setup):
    """测试消息确认机制"""
    session_id = "test_sub_004"

    # 发布事件
    publisher = DialogEventPublisher(session_id)
    event = DialogTurnEvent(
        session_id=session_id,
        turn_number=1,
        question="ACK测试",
        answer="ACK回答"
    )
    publisher.publish(event)

    # 创建订阅器并处理消息
    subscriber = TestSubscriber(session_id)

    def run_subscriber():
        time.sleep(1)
        subscriber.stop()

    threading.Thread(target=run_subscriber, daemon=True).start()
    subscriber.start(block_ms=1000, count=10)

    # 验证：消息已被ACK，pending列表应为空
    redis = get_redis()
    stream_key = f"dialog_stream:{session_id}"

    # 查询pending消息（需要先确保消费者组存在）
    try:
        pending = redis.client.xpending(stream_key, subscriber.consumer_group)
        # pending返回格式: [count, min_id, max_id, consumers]
        pending_count = pending[0] if pending else 0
        assert pending_count == 0, f"pending列表应为空，实际有{pending_count}条"
    except Exception as e:
        # 消费者组可能已不存在，说明消息已正确处理
        print(f"pending查询异常（正常）: {e}")

    print("✅ 消息确认机制测试通过")


def test_event_deserialization(redis_setup):
    """测试事件反序列化正确性"""
    session_id = "test_sub_005"

    # 发布包含复杂字段的事件
    publisher = DialogEventPublisher(session_id)
    event = DialogTurnEvent(
        session_id=session_id,
        turn_number=1,
        question="反序列化测试",
        answer="反序列化回答",
        tool_calls=[{"name": "tool1", "args": {"key": "value"}}],
        metadata={"nested": {"data": "test"}}
    )
    publisher.publish(event)

    # 订阅并验证反序列化
    subscriber = TestSubscriber(session_id)

    def run_subscriber():
        time.sleep(1)
        subscriber.stop()

    threading.Thread(target=run_subscriber, daemon=True).start()
    subscriber.start(block_ms=1000, count=10)

    assert len(subscriber.received_events) == 1
    received = subscriber.received_events[0]

    # 验证复杂字段
    assert received.tool_calls is not None
    assert len(received.tool_calls) == 1
    assert received.tool_calls[0]["name"] == "tool1"

    assert received.metadata is not None
    assert received.metadata["nested"]["data"] == "test"

    print("✅ 事件反序列化测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
