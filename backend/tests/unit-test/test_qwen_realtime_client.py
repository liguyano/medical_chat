import asyncio
import base64
import json

import pytest

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

    events = [event async for event in client.events()]
    assert events[0]["type"] == "response.audio.delta"
    assert events[0]["delta"]
    assert events[1] == {
        "type": "response.audio.delta.binary",
        "audio": b"binary-pcm",
    }
    assert events[2]["type"] == "response.done"
    assert websocket.sent[-1]["type"] == "input_audio_buffer.append"
    assert base64.b64decode(websocket.sent[-1]["audio"]) == b"input"
