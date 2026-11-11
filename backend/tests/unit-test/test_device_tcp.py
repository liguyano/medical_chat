import asyncio
import struct

import pytest

from app.services.device_tcp import read_frame


def test_tcp_frames_can_arrive_split_or_coalesced():
    async def check():
        reader = asyncio.StreamReader()
        reader.feed_data(b"\x01")
        reader.feed_data(struct.pack("!I", 2) + b"{}" + struct.pack("!BI", 2, 2) + b"\0\0")
        assert await read_frame(reader) == (1, b"{}")
        assert await read_frame(reader) == (2, b"\0\0")

    asyncio.run(check())


def test_tcp_rejects_oversized_frame_before_reading_payload():
    async def check():
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack("!BI", 2, 100_000))
        with pytest.raises(ValueError):
            await read_frame(reader)

    asyncio.run(check())

def test_authenticated_device_can_poll_assignment_and_ping(monkeypatch):
    import base64
    import hashlib
    import json
    from types import SimpleNamespace

    from app.api import voice_dialog

    from app.services import device_tcp

    monkeypatch.setenv("DEVICE_TCP_CREDENTIALS", json.dumps({
        "ESP32-001": hashlib.sha256(b"synthetic-secret").hexdigest(),
    }))
    monkeypatch.setattr(device_tcp, "current_task", lambda _: ("TASK-1", "SESS-1", "ready"))

    session = SimpleNamespace(
        session_no="SESS-1", connected_clients=set(), turn_detection="manual", closed=False
    )
    received = []

    class FakeGateway:
        async def get_or_create(self, **kwargs):
            assert kwargs["manual_input"]
            return session

        async def attach(self, session, client):
            session.connected_clients.add(client)

        async def append_audio(self, session, body):
            received.append(body)

        async def commit(self, session):
            client = next(iter(session.connected_clients))
            await client.send_json({
                "type": "audio", "sample_rate": 24000,
                "audio_base64": base64.b64encode(b"\0\0" * 24).decode(),
            })
            await client.send_json({"type": "state", "state": "listening"})

        async def close(self, session_no):
            assert session_no == "SESS-1"

    monkeypatch.setattr(voice_dialog, "_load_session", lambda *a, **k: (1, 2, 3, {}, []))
    monkeypatch.setattr("app.services.voice_gateway.voice_gateway", FakeGateway())

    async def check():
        server = await asyncio.start_server(device_tcp.handle_device, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                for payload, expected in [
                    ({"type": "HELLO", "version": 1, "device_id": "ESP32-001",
                      "secret": "synthetic-secret"}, {"type": "HELLO_OK"}),
                    ({"type": "GET_TASK"}, {"type": "TASK", "task_no": "TASK-1", "ready": True}),
                    ({"type": "PING"}, {"type": "PONG"}),
                    ({"type": "START"}, {"type": "STARTED"}),
                    ({"type": "RECORD_START"}, {"type": "RECORDING"}),
                ]:
                    body = json.dumps(payload).encode()
                    writer.write(struct.pack("!BI", 1, len(body)) + body)
                    await writer.drain()
                    kind, reply = await asyncio.wait_for(read_frame(reader), 3)
                    assert kind == 1
                    assert json.loads(reply) == expected

                pcm = b"\0\0" * 16
                end = b'{"type":"RECORD_END"}'
                writer.write(struct.pack("!BI", 2, len(pcm)) + pcm)
                writer.write(struct.pack("!BI", 1, len(end)) + end)
                await writer.drain()
                assert json.loads((await asyncio.wait_for(read_frame(reader), 3))[1]) == {
                    "type": "PLAY_START", "sample_rate": 16000
                }
                kind, pcm_reply = await asyncio.wait_for(read_frame(reader), 3)
                assert (kind, len(pcm_reply)) == (2, 32)
                assert json.loads((await asyncio.wait_for(read_frame(reader), 3))[1]) == {
                    "type": "PLAY_END"
                }
                assert received == [pcm]
            finally:
                writer.close()
                await writer.wait_closed()

    asyncio.run(check())
