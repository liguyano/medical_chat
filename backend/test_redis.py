"""测试Redis客户端功能"""
import sys
import os

# 设置UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append('.')

from app.utils.redis_client import RedisClient
import time

def test_redis_basic():
    """测试基本缓存操作"""
    print("=== 测试1: 基本缓存操作 ===")
    client = RedisClient(host="localhost", port=6379, db=0)

    # 测试连接
    assert client.ping(), "Redis连接失败"
    print("✅ Redis连接成功")

    # 测试SET/GET
    test_key = "test:basic"
    test_value = {"name": "张三", "age": 30, "tags": ["tag1", "tag2"]}
    client.set(test_key, test_value, ex=10)

    result = client.get(test_key)
    assert result == test_value, f"数据不匹配: {result}"
    print(f"✅ SET/GET成功: {result}")

    # 测试TTL
    ttl = client.ttl(test_key)
    assert 0 < ttl <= 10, f"TTL异常: {ttl}"
    print(f"✅ TTL正常: {ttl}秒")

    # 测试DELETE
    client.delete(test_key)
    assert client.get(test_key) is None, "删除失败"
    print("✅ DELETE成功")

    client.close()
    print()


def test_redis_stream():
    """测试Stream操作"""
    print("=== 测试2: Redis Stream操作 ===")
    client = RedisClient(host="localhost", port=6379, db=0)

    stream_key = "test:stream"

    # 清理旧数据
    client.delete(stream_key)

    # 测试XADD
    message_id1 = client.xadd(stream_key, {
        "event_type": "dialog_message",
        "session_id": "sess_test_123",
        "content": "你好，我是患者",
        "metadata": {"turn": 1, "timestamp": time.time()}
    })
    print(f"✅ XADD成功: {message_id1}")

    # 添加第二条消息
    message_id2 = client.xadd(stream_key, {
        "event_type": "dialog_message",
        "session_id": "sess_test_123",
        "content": "我今天感觉不舒服",
        "metadata": {"turn": 2, "timestamp": time.time()}
    })
    print(f"✅ XADD成功: {message_id2}")

    # 测试XREAD
    messages = client.xread({stream_key: '0'}, count=10)
    assert len(messages) > 0, "读取Stream失败"

    stream_name, message_list = messages[0]
    assert len(message_list) == 2, f"消息数量不正确: {len(message_list)}"
    print(f"✅ XREAD成功: 读取到{len(message_list)}条消息")

    for msg_id, fields in message_list:
        print(f"  - ID: {msg_id.decode('utf-8')}")
        print(f"    event_type: {fields[b'event_type'].decode('utf-8')}")
        print(f"    content: {fields[b'content'].decode('utf-8')}")

    # 清理测试数据
    client.delete(stream_key)
    client.close()
    print()


def test_redis_consumer_group():
    """测试消费者组"""
    print("=== 测试3: Redis消费者组 ===")
    client = RedisClient(host="localhost", port=6379, db=0)

    stream_key = "test:stream:group"
    group_name = "test_group"
    consumer_name = "consumer_1"

    # 清理旧数据
    client.delete(stream_key)

    # 先添加一些消息
    for i in range(3):
        client.xadd(stream_key, {
            "message_no": str(i + 1),
            "content": f"测试消息{i + 1}"
        })

    # 创建消费者组
    try:
        client.xgroup_create(stream_key, group_name, id='0')
        print(f"✅ 消费者组创建成功: {group_name}")
    except Exception as e:
        print(f"⚠️  消费者组已存在或创建失败: {e}")

    # 使用消费者组读取消息
    messages = client.xreadgroup(
        group_name=group_name,
        consumer_name=consumer_name,
        streams={stream_key: '>'},  # '>'表示读取未消费的消息
        count=10,
        block=1000  # 阻塞1秒
    )

    if messages:
        stream_name, message_list = messages[0]
        print(f"✅ XREADGROUP成功: 读取到{len(message_list)}条消息")

        # 确认消息
        message_ids = [msg_id for msg_id, _ in message_list]
        client.xack(stream_key, group_name, *message_ids)
        print(f"✅ XACK成功: 确认{len(message_ids)}条消息")
    else:
        print("⚠️  没有未消费的消息")

    # 清理测试数据
    client.delete(stream_key)
    client.close()
    print()


if __name__ == "__main__":
    try:
        test_redis_basic()
        test_redis_stream()
        test_redis_consumer_group()
        print("=" * 50)
        print("🎉 所有Redis测试通过！")
        print("=" * 50)
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
