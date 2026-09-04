"""Dialog Agent 双引擎单元测试。"""

import base64
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from medagent.agents.service_agent.dialog_agent.engine import (
    DoubaoVoiceEngine,
    TextChatEngine,
)


class FakeWebSocket:
    """可控 WebSocket 测试替身。"""

    def __init__(self, responses=()):
        self.responses = deque(responses)
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        item = self.responses.popleft()
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self):
        self.closed = True


class FakeConnector:
    """记录 websockets.connect 参数。"""

    def __init__(self, websocket):
        self.websocket = websocket
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.websocket


def voice_engine(websocket):
    connector = FakeConnector(websocket)
    engine = DoubaoVoiceEngine(
        api_key="voice-key",
        model="voice-model",
        ws_url="wss://voice.example/ws",
        timeout=0.1,
        connector=connector,
    )
    return engine, connector


def test_doubao_validates_reconnect_attempts_and_socket_state():
    """重连次数和 websockets 新旧版本连接状态都应被正确识别。"""
    with pytest.raises(ValueError, match="不能小于 0"):
        DoubaoVoiceEngine(api_key="key", reconnect_attempts=-1)

    assert DoubaoVoiceEngine._is_open(None) is False
    assert DoubaoVoiceEngine._is_open(SimpleNamespace()) is True
    assert DoubaoVoiceEngine._is_open(
        SimpleNamespace(state=SimpleNamespace(name="OPEN"))
    )
    assert DoubaoVoiceEngine._is_open(SimpleNamespace(state=1))
    assert not DoubaoVoiceEngine._is_open(
        SimpleNamespace(state=SimpleNamespace(name="CLOSED"))
    )


@pytest.mark.asyncio
async def test_doubao_create_session_uses_websockets_17_contract():
    """创建会话应使用 additional_headers 并发送完整 session.create。"""
    websocket = FakeWebSocket([json.dumps({"type": "session.created"})])
    engine, connector = voice_engine(websocket)

    await engine.create_session(
        "system prompt",
        [{"type": "function", "function": {"name": "tool"}}],
        voice="voice-a",
        audio_format="opus",
    )

    url, kwargs = connector.calls[0]
    assert url == "wss://voice.example/ws"
    assert kwargs["additional_headers"]["Authorization"] == "Bearer voice-key"
    assert "extra_headers" not in kwargs
    payload = websocket.sent[0]
    assert payload["type"] == "session.create"
    assert payload["model"] == "voice-model"
    assert payload["conversation_id"]
    assert payload["voice"] == "voice-a"
    assert payload["audio_format"]["type"] == "opus"


@pytest.mark.asyncio
async def test_doubao_accepts_binary_session_ack():
    """部分 WebSocket 实现返回 bytes ACK 时也应创建成功。"""
    websocket = FakeWebSocket([json.dumps({"type": "session.created"}).encode()])
    engine, _ = voice_engine(websocket)

    await engine.create_session("prompt", [])

    assert engine.session_id


@pytest.mark.asyncio
async def test_doubao_create_session_rejects_invalid_ack_and_closes():
    """服务端未确认会话时应失败并关闭连接。"""
    websocket = FakeWebSocket([json.dumps({"type": "error"})])
    engine, _ = voice_engine(websocket)

    with pytest.raises(RuntimeError, match="会话创建失败"):
        await engine.create_session("prompt", [])

    assert websocket.closed is True
    assert engine.websocket is None


@pytest.mark.asyncio
async def test_doubao_send_input_encodes_pcm_and_commits():
    """PCM 输入应按 append/commit 两条消息发送。"""
    websocket = FakeWebSocket([json.dumps({"type": "session.created"})])
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    await engine.send_input(b"\x01\x02")

    assert websocket.sent[-2] == {
        "type": "input.audio.buffer.append",
        "audio": base64.b64encode(b"\x01\x02").decode(),
    }
    assert websocket.sent[-1] == {"type": "input.audio.buffer.commit"}


@pytest.mark.asyncio
async def test_doubao_rejects_non_bytes_input():
    """语音引擎不得隐式接受文本。"""
    websocket = FakeWebSocket([json.dumps({"type": "session.created"})])
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    with pytest.raises(TypeError, match="PCM bytes"):
        await engine.send_input("not audio")


@pytest.mark.asyncio
async def test_doubao_normalizes_all_stream_events():
    """豆包协议事件应归一化为 SDK 统一事件。"""
    raw_audio = b"\x10\x20"
    websocket = FakeWebSocket(
        [
            json.dumps({"type": "session.created"}),
            json.dumps(
                {
                    "type": "input.audio.transcription.completed",
                    "transcript": "我吸烟",
                }
            ),
            json.dumps({"type": "response.text.delta", "delta": "好的"}),
            json.dumps(
                {
                    "type": "response.audio.delta",
                    "delta": base64.b64encode(raw_audio).decode(),
                }
            ),
            json.dumps(
                {
                    "type": "response.function_call",
                    "call_id": "call-1",
                    "name": "get_education_material",
                    "arguments": '{"category":"tobacco"}',
                }
            ),
            json.dumps({"type": "response.done"}),
        ]
    )
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    events = [event async for event in engine.stream_response()]

    assert [event["type"] for event in events] == [
        "user_transcript",
        "text",
        "audio",
        "tool_call",
        "response_done",
    ]
    assert events[2]["data"] == raw_audio
    assert events[3]["arguments"] == {"category": "tobacco"}


@pytest.mark.asyncio
async def test_doubao_binary_frame_is_audio():
    """二进制帧必须直接作为音频，不得按 JSON 字典处理。"""
    websocket = FakeWebSocket(
        [json.dumps({"type": "session.created"}), b"binary-audio"]
    )
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    event = await anext(engine.stream_response())

    assert event == {"type": "audio", "data": b"binary-audio"}


@pytest.mark.asyncio
async def test_doubao_invalid_tool_json_becomes_error_event():
    """损坏工具参数不得击穿事件循环。"""
    websocket = FakeWebSocket(
        [
            json.dumps({"type": "session.created"}),
            json.dumps(
                {
                    "type": "response.function_call",
                    "call_id": "call-1",
                    "name": "tool",
                    "arguments": "{broken",
                }
            ),
        ]
    )
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    events = [event async for event in engine.stream_response()]

    assert events == [{"type": "error", "message": "工具参数不是合法 JSON"}]


@pytest.mark.asyncio
async def test_doubao_timeout_becomes_error_event():
    """接收超时应产生可处理的统一错误事件。"""
    websocket = FakeWebSocket(
        [json.dumps({"type": "session.created"}), TimeoutError()]
    )
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    events = [event async for event in engine.stream_response()]

    assert events == [{"type": "error", "message": "响应超时"}]


@pytest.mark.asyncio
async def test_doubao_reports_disconnected_and_malformed_stream_messages():
    """未连接、非法 JSON、非对象和供应商错误应归一化为错误事件。"""
    disconnected, _ = voice_engine(None)
    assert [event async for event in disconnected.stream_response()] == [
        {"type": "error", "message": "WebSocket 未连接"}
    ]

    cases = [
        ("not-json", "WebSocket 消息不是合法 JSON"),
        (json.dumps(["not", "object"]), "WebSocket 消息格式错误"),
        (
            json.dumps({"type": "response.audio.delta", "delta": "%"}),
            "音频数据不是合法 base64",
        ),
        (
            json.dumps(
                {
                    "type": "response.function_call",
                    "call_id": "call",
                    "name": "tool",
                    "arguments": [],
                }
            ),
            "工具参数格式错误",
        ),
        (
            json.dumps({"type": "error", "message": "供应商错误"}),
            "供应商错误",
        ),
    ]
    for raw_message, expected_message in cases:
        websocket = FakeWebSocket(
            [json.dumps({"type": "session.created"}), raw_message]
        )
        engine, _ = voice_engine(websocket)
        await engine.create_session("prompt", [])
        assert [event async for event in engine.stream_response()] == [
            {"type": "error", "message": expected_message}
        ]


@pytest.mark.asyncio
async def test_doubao_tool_result_update_and_close_are_serialized():
    """工具结果、动态约束和关闭消息格式应稳定。"""
    websocket = FakeWebSocket([json.dumps({"type": "session.created"})])
    engine, _ = voice_engine(websocket)
    await engine.create_session("prompt", [])

    await engine.send_tool_result("call-1", {"ok": True})
    await engine.update_session(instructions="回到评估", tools=[])
    await engine.close_session()
    await engine.close_session()

    assert websocket.sent[-3]["item"]["call_id"] == "call-1"
    assert websocket.sent[-2]["type"] == "session.update"
    assert websocket.sent[-2]["instructions"] == "回到评估"
    assert websocket.sent[-1]["type"] == "session.close"
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_doubao_rejects_operations_without_required_connection():
    """缺少 call_id 或连接时不得静默丢失工具结果和约束。"""
    engine, _ = voice_engine(None)

    with pytest.raises(ValueError, match="call_id"):
        await engine.send_tool_result("", {})
    with pytest.raises(RuntimeError, match="未连接"):
        await engine.send_tool_result("call", {})
    with pytest.raises(RuntimeError, match="未连接"):
        await engine.update_session(instructions="约束")
    with pytest.raises(RuntimeError, match="未连接"):
        await engine.send_input(b"pcm")


def chunk(*, content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=tool_calls)
            )
        ]
    )


def tool_delta(index, *, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


async def async_chunks(items):
    for item in items:
        yield item


def text_engine(items):
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=async_chunks(items))
            )
        ),
        close=AsyncMock(),
    )
    engine = TextChatEngine(
        api_key="key",
        model="model",
        api_base="https://example.com/v1",
        client=client,
    )
    return engine, client


def text_engine_with_options(items):
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=async_chunks(items))
            )
        ),
        close=AsyncMock(),
    )
    engine = TextChatEngine(
        api_key="key",
        model="model",
        api_base="https://example.com/v1",
        request_options={
            "temperature": 0.1,
            "max_tokens": 321,
            "extra_body": {"enable_thinking": False},
        },
        client=client,
    )
    return engine, client


def empty_chunk():
    return SimpleNamespace(choices=[])


@pytest.mark.asyncio
async def test_text_engine_streams_text_and_preserves_history():
    """文本流应逐片输出并保存完整 assistant 消息。"""
    engine, client = text_engine([chunk(content="您"), chunk(content="好")])
    await engine.create_session("system", [])
    await engine.send_input("你好")

    events = [event async for event in engine.stream_response()]

    assert events == [
        {"type": "text", "content": "您好"},
        {"type": "response_done"},
    ]
    assert engine.messages[-1] == {"role": "assistant", "content": "您好"}
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_text_engine_ignores_empty_usage_chunk():
    """DashScope 末尾的 choices 为空的用量 chunk 不应导致真实响应失败。"""
    engine, _ = text_engine([chunk(content="ok"), empty_chunk()])
    await engine.create_session("system", [])
    await engine.send_input("hello")

    events = [event async for event in engine.stream_response()]

    assert events == [
        {"type": "text", "content": "ok"},
        {"type": "response_done"},
    ]


@pytest.mark.asyncio
async def test_text_engine_passes_real_model_request_options():
    """TextChatEngine 应把配置的真实模型参数透传到 Chat Completions。"""
    engine, client = text_engine_with_options([chunk(content="ok")])
    await engine.create_session("system", [])
    await engine.send_input("hello")

    events = [event async for event in engine.stream_response()]

    assert events[-1] == {"type": "response_done"}
    request = client.chat.completions.create.await_args.kwargs
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == 321
    assert request["extra_body"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_text_engine_aggregates_chunked_tool_call():
    """OpenAI 流式工具名称和参数分片应合并后只发布一次。"""
    engine, _ = text_engine(
        [
            chunk(
                tool_calls=[
                    tool_delta(
                        0,
                        call_id="call-1",
                        name="get_education_",
                        arguments='{"category":"tob',
                    )
                ]
            ),
            chunk(
                tool_calls=[
                    tool_delta(
                        0,
                        name="material",
                        arguments='acco","level":2}',
                    )
                ]
            ),
        ]
    )
    await engine.create_session("system", [])
    await engine.send_input("我吸烟")

    events = [event async for event in engine.stream_response()]

    assert events[0] == {
        "type": "tool_call",
        "call_id": "call-1",
        "name": "get_education_material",
        "arguments": {"category": "tobacco", "level": 2},
    }
    assert events[-1] == {"type": "response_done"}
    assert engine.messages[-1]["tool_calls"][0]["id"] == "call-1"


@pytest.mark.asyncio
async def test_text_engine_invalid_tool_json_becomes_error():
    """工具参数分片损坏时应返回 error，不发布半成品调用。"""
    engine, _ = text_engine(
        [
            chunk(
                tool_calls=[
                    tool_delta(
                        0,
                        call_id="call-1",
                        name="tool",
                        arguments="{broken",
                    )
                ]
            )
        ]
    )
    await engine.create_session("system", [])

    events = [event async for event in engine.stream_response()]

    assert events == [{"type": "error", "message": "工具参数不是合法 JSON"}]


@pytest.mark.asyncio
async def test_text_engine_rejects_incomplete_tool_call():
    """缺少调用 ID 或函数名的模型分片不得进入工具执行。"""
    engine, _ = text_engine(
        [chunk(tool_calls=[tool_delta(0, name="tool", arguments="{}")])]
    )
    await engine.create_session("system", [])

    events = [event async for event in engine.stream_response()]

    assert events == [{"type": "error", "message": "工具调用信息不完整"}]


@pytest.mark.asyncio
async def test_text_engine_rejects_audio_and_closes_client():
    """文本引擎拒绝音频，并在关闭时释放 OpenAI 客户端。"""
    engine, client = text_engine([])
    await engine.create_session("system", [])
    with pytest.raises(TypeError, match="文本输入"):
        await engine.send_input(b"audio")

    await engine.close_session()

    client.close.assert_awaited_once()
    assert engine.messages == []


@pytest.mark.asyncio
async def test_text_engine_tool_result_and_session_update():
    """工具结果和动态约束应追加到文本上下文并更新工具表。"""
    engine, _ = text_engine([])
    await engine.create_session("system", [{"name": "old"}])

    with pytest.raises(ValueError, match="call_id"):
        await engine.send_tool_result("", {})
    await engine.send_tool_result("call-1", {"ok": True})
    await engine.update_session(instructions="回到评估", tools=[{"name": "new"}])

    assert engine.messages[-2] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"ok": true}',
    }
    assert engine.messages[-1] == {"role": "system", "content": "回到评估"}
    assert engine.tools == [{"name": "new"}]


@pytest.mark.asyncio
async def test_text_engine_model_failure_becomes_generic_error():
    """模型异常不得把供应商错误文本泄漏给患者主流程。"""
    engine, client = text_engine([])
    client.chat.completions.create.side_effect = RuntimeError("secret upstream")
    await engine.create_session("system", [])

    events = [event async for event in engine.stream_response()]

    assert events == [{"type": "error", "message": "文本模型调用失败"}]


@pytest.mark.asyncio
async def test_text_engine_discards_everything_before_think_close_marker():
    """发现 </think> 时，应丢弃它以及之前的所有内容，只保留患者正文。"""
    engine, _ = text_engine(
        [
            chunk(content="Picking a question from the candidates."),
            chunk(content=" Let me report the choice first.</think>"),
            chunk(content="好的，我们继续下一题。"),
        ]
    )
    await engine.create_session("system", [])
    await engine.send_input("继续")

    events = [event async for event in engine.stream_response()]

    assert events == [
        {"type": "text", "content": "好的，我们继续下一题。"},
        {"type": "response_done"},
    ]
    assert engine.messages[-1] == {
        "role": "assistant",
        "content": "好的，我们继续下一题。",
    }


@pytest.mark.asyncio
async def test_text_engine_handles_think_close_marker_split_across_chunks():
    """</think> 被拆成多个 chunk 时，也应丢弃此前全部内部思考。"""
    engine, _ = text_engine(
        [
            chunk(content="internal planning"),
            chunk(content=" and tool choice</th"),
            chunk(content="ink>好"),
            chunk(content="的"),
        ]
    )
    await engine.create_session("system", [])
    await engine.send_input("继续")

    events = [event async for event in engine.stream_response()]

    assert events == [
        {"type": "text", "content": "好"},
        {"type": "text", "content": "的"},
        {"type": "response_done"},
    ]
    assert engine.messages[-1] == {"role": "assistant", "content": "好的"}


@pytest.mark.asyncio
async def test_text_engine_preserves_plain_response_when_no_think_close_marker():
    """整轮没有 </think> 时，不得误删正常模型回复。"""
    engine, _ = text_engine([chunk(content="好的，"), chunk(content="继续下一题。")])
    await engine.create_session("system", [])
    await engine.send_input("继续")

    events = [event async for event in engine.stream_response()]

    assert events == [
        {"type": "text", "content": "好的，继续下一题。"},
        {"type": "response_done"},
    ]
    assert engine.messages[-1] == {
        "role": "assistant",
        "content": "好的，继续下一题。",
    }
