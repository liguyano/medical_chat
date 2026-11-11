import hashlib
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api import devices


def test_device_auth_requires_the_matching_secret(monkeypatch):
    monkeypatch.setenv("DEVICE_HTTP_CREDENTIALS", '{"ESP32-001":"' +
                       hashlib.sha256(b"test-secret").hexdigest() + '"}')
    db = Mock()
    db.get.return_value = None
    assert devices.authenticate_device("ESP32-001", "test-secret", db) == "ESP32-001"
    with pytest.raises(HTTPException) as error:
        devices.authenticate_device("ESP32-001", "wrong", db)
    assert error.value.status_code == 401


def test_heartbeat_sets_45_second_online_status(monkeypatch):
    redis = Mock()
    monkeypatch.setattr(devices, "get_redis", lambda: redis)
    assert devices.heartbeat("ESP32-001") == {"online": True}
    redis.set.assert_called_once_with("device_http:online:ESP32-001", "1", ex=45)


def test_http_round_upload_poll_download_and_isolation(monkeypatch):
    import base64
    import io
    import time
    import wave
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    secret_hash = hashlib.sha256(b"test-secret").hexdigest()
    monkeypatch.setenv(
        "DEVICE_HTTP_CREDENTIALS", f'{{"D1":"{secret_hash}","D2":"{secret_hash}"}}'
    )
    monkeypatch.setattr(devices, "current_task", lambda _: ("TASK-1", "SESSION-1", "ready"))
    monkeypatch.setattr(devices, "_load_session", lambda *a, **k: (1, 1, 1, {}, []))
    monkeypatch.setattr(devices, "rounds", {})
    sent = []

    class FakeGateway:
        async def get_or_create(self, **kwargs):
            assert kwargs["manual_input"]
            return SimpleNamespace(connected_clients=set(), turn_detection="manual")

        async def attach(self, session, reply):
            session.connected_clients.add(reply)

        async def append_audio(self, session, pcm):
            sent.append(pcm)

        async def commit(self, session):
            reply = next(iter(session.connected_clients))
            await reply.send_json({
                "type": "audio", "sample_rate": 24000,
                "audio_base64": base64.b64encode(b"\0\0" * 24).decode(),
            })
            await reply.send_json({"type": "state", "state": "listening"})

        async def close(self, session_no):
            assert session_no == "SESSION-1"

    monkeypatch.setattr(devices, "voice_gateway", FakeGateway())
    app = FastAPI()
    app.include_router(devices.router)
    db = Mock()
    db.get.return_value = None
    app.dependency_overrides[devices.get_db] = lambda: db
    headers = {
        "X-Device-ID": "D1", "X-Device-Secret": "test-secret",
        "Content-Type": "application/octet-stream",
    }
    path = "/api/device/tasks/TASK-1/turns/turn-1"
    with TestClient(app) as client:
        assert client.get("/api/device/task", headers=headers).json()["ready"]
        assert client.put(path, headers=headers, content=b"\0").status_code == 422
        pcm = b"\0\0" * 16
        assert client.put(path, headers=headers, content=pcm).status_code == 202
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = client.get(path, headers=headers).json()["status"]
            if status != "processing":
                break
            time.sleep(0.01)
        assert status == "ready"
        assert client.put(path, headers=headers, content=pcm).status_code == 202
        assert sent == [pcm]
        assert client.put(path, headers=headers, content=b"\1\0").status_code == 409
        reply = client.get(path + "/audio", headers=headers)
        assert reply.status_code == 200
        with wave.open(io.BytesIO(reply.content), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
            assert wav.getnframes() == 16
        assert client.get(path + "/audio", headers={**headers, "X-Device-ID": "D2"}).status_code == 404
