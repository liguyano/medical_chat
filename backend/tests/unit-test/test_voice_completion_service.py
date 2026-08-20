"""实时语音评估完成屏障测试。"""

from types import SimpleNamespace
from unittest.mock import Mock

from app.services import voice_completion_service as completion_module
from app.services.voice_completion_service import VoiceCompletionCoordinator


class FakeRedis:
    """支持完成协调器所需命令的内存 Redis 替身。"""

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


def test_assessment_completion_waits_for_matching_response(monkeypatch):
    """Extraction 先完成时不得提前结束，必须等最后一轮回复完成。"""
    redis = FakeRedis()
    finalize = Mock(return_value=True)
    monkeypatch.setattr(completion_module, "_latest_patient_turn", lambda _: 4)
    monkeypatch.setattr(
        completion_module,
        "finalize_voice_assessment_session",
        finalize,
    )
    coordinator = VoiceCompletionCoordinator(redis)

    assert (
        coordinator.mark_assessment_completed(session_id="SESS-1", task_id=7)
        is False
    )
    finalize.assert_not_called()

    assert (
        coordinator.mark_response_completed(
            session_id="SESS-1",
            task_id=7,
            response_turn=5,
            response_id="resp-5",
            generation_id="gen-5",
        )
        is True
    )
    finalize.assert_called_once_with(session_id="SESS-1", task_id=7)


def test_old_response_done_cannot_complete_new_patient_turn(monkeypatch):
    """历史 response.done 不能满足新患者答案对应的完成屏障。"""
    redis = FakeRedis()
    finalize = Mock(return_value=True)
    monkeypatch.setattr(completion_module, "_latest_patient_turn", lambda _: 6)
    monkeypatch.setattr(
        completion_module,
        "finalize_voice_assessment_session",
        finalize,
    )
    coordinator = VoiceCompletionCoordinator(redis)

    coordinator.mark_response_completed(
        session_id="SESS-2",
        task_id=8,
        response_turn=6,
    )
    assert (
        coordinator.mark_assessment_completed(session_id="SESS-2", task_id=8)
        is False
    )
    finalize.assert_not_called()

    assert (
        coordinator.mark_response_completed(
            session_id="SESS-2",
            task_id=8,
            response_turn=7,
        )
        is True
    )


def test_response_done_first_then_extraction_finalizes_once(monkeypatch):
    """response.done 先到时，Extraction 完成后仍能收尾且重复回调不重复执行。"""
    redis = FakeRedis()
    finalize = Mock(return_value=True)
    monkeypatch.setattr(completion_module, "_latest_patient_turn", lambda _: 2)
    monkeypatch.setattr(
        completion_module,
        "finalize_voice_assessment_session",
        finalize,
    )
    coordinator = VoiceCompletionCoordinator(redis)

    assert (
        coordinator.mark_response_completed(
            session_id="SESS-3",
            task_id=9,
            response_turn=3,
        )
        is False
    )
    assert (
        coordinator.mark_assessment_completed(session_id="SESS-3", task_id=9)
        is True
    )
    assert (
        coordinator.mark_response_completed(
            session_id="SESS-3",
            task_id=9,
            response_turn=3,
        )
        is True
    )
    finalize.assert_called_once_with(session_id="SESS-3", task_id=9)


def test_completed_database_session_republishes_stable_end_event(monkeypatch):
    """进程在提交数据库后异常时，重试应使用稳定事件编号补发结束事件。"""

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalar(self, statement):
            if "max" in str(statement).lower():
                return 5
            return SimpleNamespace(
                id=10,
                task_id=7,
                session_status="completed",
            )

    published: list[object] = []
    monkeypatch.setattr(
        completion_module.model_base,
        "SessionLocal",
        lambda: FakeDb(),
    )
    monkeypatch.setattr(
        completion_module,
        "complete_assessment_session",
        lambda _db, _session_id: SimpleNamespace(completed=True),
    )
    monkeypatch.setattr(
        completion_module,
        "DialogEventPublisher",
        lambda _session_id: SimpleNamespace(
            publish=lambda event: published.append(event)
        ),
    )

    assert completion_module.finalize_voice_assessment_session(
        session_id="SESS-RECOVER",
        task_id=7,
    )
    assert published[0].event_id == "VOICE-SESSION-END-SESS-RECOVER"
