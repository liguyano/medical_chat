from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

import app.services.patient_portal_service as portal
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get_and_delete(self, key: str):
        return self.values.pop(key, None)

    def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


def make_request(host: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/patients/verify-task",
        "raw_path": b"/api/patients/verify-task",
        "query_string": b"",
        "headers": [],
        "client": (host, 12345),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


def test_patient_assistant_message_number_is_stable_and_bounded():
    first = portal._patient_assistant_message_no("client-message-" + "x" * 500)
    second = portal._patient_assistant_message_no("client-message-" + "x" * 500)

    assert first == second
    assert first.startswith("PATIENT-")
    assert len(first) <= 64
    assert len(portal._patient_assistant_message_no(None)) <= 64


def test_verify_task_identity_success_clears_rate_limit(monkeypatch):
    redis = FakeRedis()
    patient = SimpleNamespace(
        id=11,
        patient_name="患者",
        id_card_ciphertext="ciphertext",
    )
    encounter = SimpleNamespace(id=22, encounter_status="在院")
    task = SimpleNamespace(id=33, task_no="TASK-001")
    monkeypatch.setattr(portal, "_check_verify_limit", lambda *_args: "rate-key")
    monkeypatch.setattr(portal, "_task_by_no", lambda *_args: (task, patient, encounter))
    monkeypatch.setattr(portal, "decrypt_id_card", lambda *_args: "11010119900101001X")
    monkeypatch.setattr(portal, "get_redis", lambda: redis)
    monkeypatch.setattr(
        portal.patient_service,
        "create_patient_session",
        lambda **kwargs: f"session-{kwargs['patient_id']}-{kwargs['encounter_id']}",
    )

    result = portal.verify_task_identity(
        Mock(),
        make_request(),
        task_no="TASK-001",
        id_card_suffix="001x",
    )

    assert result == (patient, encounter, task, "session-11-22")
    assert redis.values == {}


def test_verify_task_identity_rejects_suffix(monkeypatch):
    patient = SimpleNamespace(id=11, id_card_ciphertext="ciphertext")
    encounter = SimpleNamespace(id=22, encounter_status="在院")
    task = SimpleNamespace(id=33, task_no="TASK-001")
    monkeypatch.setattr(portal, "_check_verify_limit", lambda *_args: "rate-key")
    monkeypatch.setattr(portal, "_task_by_no", lambda *_args: (task, patient, encounter))
    monkeypatch.setattr(portal, "decrypt_id_card", lambda *_args: "110101199001010011")

    with pytest.raises(AppError) as raised:
        portal.verify_task_identity(
            Mock(),
            make_request(),
            task_no="TASK-001",
            id_card_suffix="9999",
        )

    assert raised.value.code == ErrorCode.ERR_PATIENT_001


def test_scan_token_is_single_use(monkeypatch):
    redis = FakeRedis()
    redis.values["patient_scan_token:" + "a" * 64] = {
        "task_id": 33,
        "encounter_id": 22,
    }
    monkeypatch.setattr(portal, "get_redis", lambda: redis)

    class FakeDb:
        def get(self, model, value):
            if value == 33:
                return SimpleNamespace(
                    id=33,
                    patient_id=11,
                    encounter_id=22,
                    deleted=0,
                )
            if value == 22:
                return SimpleNamespace(id=22, patient_id=11, encounter_status="在院", deleted=0)
            if value == 11:
                return SimpleNamespace(id=11, deleted=0, patient_name="患者")
            return None

    # Bypass the hash calculation only to exercise the atomic consume contract.
    token = "token"
    digest = portal.hashlib.sha256(token.encode()).hexdigest()
    redis.values[f"patient_scan_token:{digest}"] = redis.values.pop(
        "patient_scan_token:" + "a" * 64
    )
    monkeypatch.setattr(
        portal.patient_service,
        "create_patient_session",
        lambda **_kwargs: "patient-session",
    )

    result = portal.consume_scan_token(FakeDb(), token)
    assert result[-1] == "patient-session"
    with pytest.raises(AppError) as raised:
        portal.consume_scan_token(FakeDb(), token)
    assert raised.value.code == ErrorCode.ERR_PATIENT_008
