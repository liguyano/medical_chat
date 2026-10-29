import asyncio
import base64
import json

import pytest
from websockets.exceptions import ConnectionClosedError

from app.services.qwen_realtime_client import QwenRealtimeClient


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.received = [
            json.dumps(
                {
                    "type": "response.audio.delta",
                    "delta": base64.b64encode(b"pcm").decode(),
                }
            ),
            b"binary-pcm",
            json.dumps({"type": "response.done"}),
        ]

    async def send(self, payload: str):
        self.sent.append(json.loads(payload))

    async def recv(self):
        if self.received:
            return self.received.pop(0)
        await asyncio.sleep(0)
        raise TimeoutError

    async def close(self):
        return None


class IdleThenEventWebSocket(FakeWebSocket):
    def __init__(self):
        super().__init__()
        self.received = [TimeoutError(), json.dumps({"type": "response.done"})]

    async def recv(self):
        item = self.received.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ClosedOnFirstSendWebSocket(FakeWebSocket):
    def __init__(self):
        super().__init__()
        self.fail_next_send = False

    async def send(self, payload: str):
        if self.fail_next_send:
            self.fail_next_send = False
            raise ConnectionClosedError(None, None, None)
        await super().send(payload)


@pytest.mark.asyncio
async def test_qwen_client_uses_official_server_vad_session_config():
    websocket = FakeWebSocket()
    connected_url = ""
    connected_options: dict = {}
    tools = [
        {
            "type": "function",
            "function": {
                "name": "request_nurse_assistance",
                "description": "呼叫护士",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    async def connector(*args, **kwargs):
        nonlocal connected_url, connected_options
        connected_url = args[0]
        connected_options = kwargs
        return websocket

    client = QwenRealtimeClient(
        api_key="key",
        model="qwen-audio-3.0-realtime-flash",
        websocket_url="wss://example/realtime",
        connector=connector,
        timeout=0.1,
    )
    await client.connect(
        instructions="问候患者",
        tools=tools,
        turn_detection="server_vad",
        vad_threshold=0.1,
        silence_duration_ms=900,
        max_history_turns=50,
    )

    assert "model=qwen-audio-3.0-realtime-flash" in connected_url
    headers = connected_options["additional_headers"]
    assert headers["Authorization"] == "Bearer key"
    assert headers["x-dashscope-dataInspection"] == "disable"

    event = websocket.sent[0]
    assert event["type"] == "session.update"
    assert event["event_id"].startswith("event_")
    assert event["session"] == {
        "modalities": ["text", "audio"],
        "voice": "longanqian",
        "instructions": "问候患者",
        "input_audio_format": "pcm",
        "output_audio_format": "pcm",
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.1,
            "silence_duration_ms": 900,
        },
        "tools": tools,
        "max_history_turns": 50,
    }


@pytest.mark.asyncio
async def test_qwen_client_sends_official_function_call_output_then_response_create():
    websocket = FakeWebSocket()

    async def connector(*_args, **_kwargs):
        return websocket

    client = QwenRealtimeClient(
        api_key="key",
        model="qwen-audio-3.0-realtime-flash",
        websocket_url="wss://example/realtime",
        connector=connector,
        timeout=0.1,
    )
    await client.connect(
        instructions="问候患者",
        tools=[],
        turn_detection="server_vad",
    )
    websocket.sent.clear()

    await client.send_tool_result(
        "call_001",
        {"success": True, "message": "护士已收到呼叫"},
    )
    await client.create_response()

    assert [event["type"] for event in websocket.sent] == [
        "conversation.item.create",
        "response.create",
    ]
    assert websocket.sent[0]["item"] == {
        "type": "function_call_output",
        "call_id": "call_001",
        "output": json.dumps(
            {"success": True, "message": "护士已收到呼叫"},
            ensure_ascii=False,
        ),
    }
    assert websocket.sent[1]["response"] == {
        "modalities": ["audio", "text"],
    }
    assert all(event["event_id"].startswith("event_") for event in websocket.sent)


@pytest.mark.asyncio
async def test_qwen_client_appends_audio_and_parses_events():
    websocket = FakeWebSocket()

    async def connector(*_args, **_kwargs):
        return websocket

    client = QwenRealtimeClient(
        api_key="key",
        model="qwen-audio-3.0-realtime-flash",
        websocket_url="wss://example/realtime",
        connector=connector,
        timeout=0.1,
    )
    await client.connect(
        instructions="问候患者",
        tools=[],
        turn_detection="server_vad",
    )
    await client.append_audio(b"input")

    event_stream = client.events()
    events = [await anext(event_stream) for _ in range(3)]
    assert events[0]["type"] == "response.audio.delta"
    assert events[0]["delta"]
    assert events[1] == {
        "type": "response.audio.delta.binary",
        "audio": b"binary-pcm",
    }
    assert events[2]["type"] == "response.done"
    assert websocket.sent[-1]["type"] == "input_audio_buffer.append"
    assert base64.b64decode(websocket.sent[-1]["audio"]) == b"input"


@pytest.mark.asyncio
async def test_qwen_client_keeps_receiving_after_idle_timeout():
    websocket = IdleThenEventWebSocket()

    async def connector(*_args, **_kwargs):
        return websocket

    client = QwenRealtimeClient(
        api_key="key",
        model="qwen-audio-3.0-realtime-flash",
        websocket_url="wss://example/realtime",
        connector=connector,
        timeout=0.1,
    )
    await client.connect(instructions="问候患者", tools=[], turn_detection="server_vad")

    event = await anext(client.events())

    assert event["type"] == "response.done"


@pytest.mark.asyncio
async def test_qwen_client_reconnects_and_retries_send_after_connection_closed():
    first = ClosedOnFirstSendWebSocket()
    second = FakeWebSocket()
    connections = [first, second]

    async def connector(*_args, **_kwargs):
        return connections.pop(0)

    client = QwenRealtimeClient(
        api_key="key",
        model="qwen-audio-3.0-realtime-flash",
        websocket_url="wss://example/realtime",
        connector=connector,
        timeout=0.1,
    )
    await client.connect(instructions="问候患者", tools=[], turn_detection="server_vad")
    await client.update_instructions("只问剩余项目")
    client.remember_turn("user", "喜欢散步，回来坐一会儿")
    client.remember_turn("assistant", "坐下再起来方便吗？")
    first.fail_next_send = True

    await client.append_audio(b"input")

    assert [event["type"] for event in second.sent] == [
        "session.update",
        "input_audio_buffer.append",
    ]
    assert base64.b64decode(second.sent[-1]["audio"]) == b"input"
    instructions = second.sent[0]["session"]["instructions"]
    assert "只问剩余项目" in instructions
    assert "喜欢散步" in instructions
    assert "不要重新自我介绍" in instructions
    assert "问候患者" not in instructions


@pytest.mark.asyncio
async def test_reconnect_failure_has_correlated_safe_diagnostics(tmp_path):
    import logging

    from app.services.voice_diagnostics import setup_voice_diagnostics

    path = tmp_path / "voice.jsonl"
    handler = setup_voice_diagnostics(path)
    first = ClosedOnFirstSendWebSocket()
    calls = 0

    async def connector(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("SECRET_PROVIDER_MESSAGE")
        return first

    client = QwenRealtimeClient(
        api_key="SECRET_KEY",
        model="test-model",
        websocket_url="wss://example/realtime",
        connector=connector,
    )
    client.diagnostic_session_id = "SESS-TEST"
    try:
        await client.connect(instructions="SECRET_PROMPT", tools=[])
        first.fail_next_send = True
        with pytest.raises(OSError):
            await client.append_audio(b"SECRET_AUDIO")
        handler.flush()
        content = path.read_text(encoding="utf-8")
        events = [json.loads(line) for line in content.splitlines()]
        assert {e["event"] for e in events} >= {
            "upstream_disconnected",
            "upstream_reconnect_start",
            "upstream_reconnect_failed",
        }
        failure = next(e for e in events if e["event"] == "upstream_reconnect_failed")
        assert failure["error_type"] == "OSError"
        assert failure["session_id"] == "SESS-TEST"
        assert failure["elapsed_ms"] >= 0
        starts = [e for e in events if e["event"] == "upstream_connect_start"]
        assert len(starts) == 2
        assert starts[0]["connection_id"] != starts[1]["connection_id"]
        assert starts[1]["previous_connection_id"] == starts[0]["connection_id"]
        assert starts[1]["last_event"] == "none"
        assert starts[1]["received_bytes"] == 0
        assert "SECRET" not in content
    finally:
        logging.getLogger("medical.voice.diagnostics").removeHandler(handler)
        handler.close()
