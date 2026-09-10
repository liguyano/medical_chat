"""固定人工审核参与实时语音完成屏障的测试。"""

from types import SimpleNamespace
from unittest.mock import Mock

from app.services import voice_completion_service as completion_module
from app.services.voice_completion_service import VoiceCompletionCoordinator


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.locks: dict[str, str] = {}

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    def get(self, key: str):
        return self.values.get(key)

    def exists(self, key: str) -> int:
        return int(key in self.values)

    def acquire_lock(self, key: str, token: str, ttl: int = 30) -> bool:
        if key in self.locks:
            return False
        self.locks[key] = token
        return True

    def release_lock(self, key: str, token: str) -> bool:
        if self.locks.get(key) != token:
            return False
        del self.locks[key]
        return True


def test_fixed_manual_review_requires_notification_and_qualifying_final_response(monkeypatch):
    """普通 response.done 不能结束含固定人工审核题的语音评估。"""
    redis = FakeRedis()
    finalize = Mock(return_value=True)
    notify = Mock(
        return_value=SimpleNamespace(item_count=2, notified=True, request_id="MANUAL-REVIEW-7")
    )
    monkeypatch.setattr(completion_module, "_latest_patient_turn", lambda _: 4)
    monkeypatch.setattr(completion_module, "_manual_review_item_count", lambda _: 2, raising=False)
    monkeypatch.setattr(
        completion_module,
        "ensure_planned_manual_review_notification",
        notify,
        raising=False,
    )
    monkeypatch.setattr(
        completion_module,
        "_is_manual_review_completion_response",
        lambda _session_id, response_turn: response_turn == 6,
        raising=False,
    )
    monkeypatch.setattr(
        completion_module,
        "finalize_voice_assessment_session",
        finalize,
    )
    coordinator = VoiceCompletionCoordinator(redis)

    assert coordinator.mark_assessment_completed(session_id="SESS-MANUAL", task_id=7) is False
    notify.assert_called_once_with("SESS-MANUAL")
    finalize.assert_not_called()

    # 第 5 轮是普通回答，即使满足最小轮次也不能越过固定人工审核播报屏障。
    assert (
        coordinator.mark_response_completed(
            session_id="SESS-MANUAL",
            task_id=7,
            response_turn=5,
            response_id="resp-5",
        )
        is False
    )
    finalize.assert_not_called()

    # 只有包含“固定人工审核已通知护士”的专门结束播报完成后才允许收尾。
    assert (
        coordinator.mark_response_completed(
            session_id="SESS-MANUAL",
            task_id=7,
            response_turn=6,
            response_id="resp-6",
        )
        is True
    )
    finalize.assert_called_once_with(session_id="SESS-MANUAL", task_id=7)


def test_no_fixed_manual_review_preserves_existing_completion_barrier(monkeypatch):
    """不含固定人工审核题的量表继续使用原有双屏障。"""
    redis = FakeRedis()
    finalize = Mock(return_value=True)
    monkeypatch.setattr(completion_module, "_latest_patient_turn", lambda _: 4)
    monkeypatch.setattr(completion_module, "_manual_review_item_count", lambda _: 0, raising=False)
    monkeypatch.setattr(
        completion_module,
        "finalize_voice_assessment_session",
        finalize,
    )
    coordinator = VoiceCompletionCoordinator(redis)

    assert coordinator.mark_assessment_completed(session_id="SESS-NORMAL", task_id=8) is False
    assert (
        coordinator.mark_response_completed(
            session_id="SESS-NORMAL",
            task_id=8,
            response_turn=5,
        )
        is True
    )
    finalize.assert_called_once_with(session_id="SESS-NORMAL", task_id=8)
