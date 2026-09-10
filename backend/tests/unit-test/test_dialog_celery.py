"""Dialog Agent Celery 预热与补偿任务单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.celery_app.tasks import dialog_agent_preheat, reconcile_pending_dialog_turns


def question():
    return QuestionTask(
        question_id=1,
        question_code="q1",
        question_name="问题",
        patient_text="请回答问题",
        question_type="文本",
        required=True,
        sort_no=1,
    )


def patch_common(monkeypatch, questions=None):
    """替换 Celery 任务的应用层依赖。"""
    import app.celery_app.runtime as runtime_module
    import app.utils.redis_client as redis_module

    order = []
    result_questions = [question()] if questions is None else questions
    redis = SimpleNamespace(
        set=Mock(return_value=True),
        get=Mock(
            return_value={
                "session_id": "session",
                "tasks": [item.model_dump(mode="json") for item in result_questions],
                "opening_guidance": "自然开场",
            }
        ),
    )
    monkeypatch.setattr(
        runtime_module,
        "ensure_worker_runtime",
        lambda: order.append("runtime"),
    )
    monkeypatch.setattr(redis_module, "get_redis", lambda: redis)
    return order, redis


def patch_factory(monkeypatch):
    """替换 SDK 工厂与运行时依赖注入函数。"""
    import app.workers.dialog_agent_runtime as runtime_module

    deps = {
        "middlewares": [],
        "state_store": object(),
        "history_store": object(),
        "tool_executor": None,
    }
    monkeypatch.setattr(
        runtime_module, "get_runtime_dependencies", lambda _sid: deps
    )

    agent = SimpleNamespace(initialize=AsyncMock())
    factory = Mock(return_value=agent)
    import medagent.agents.factory as factory_module

    monkeypatch.setattr(factory_module, "create_dialog_agent", factory)
    return deps, agent, factory


def test_dialog_preheat_rejects_missing_scale_codes():
    """缺少量表编码时应快速失败且不初始化外部依赖。"""
    result = dialog_agent_preheat.run("session", {}, {})

    assert result == {"status": "failed", "reason": "missing_scale_codes"}


def test_dialog_preheat_text_engine_uses_factory(monkeypatch):
    """text 模式应完成量表校验并保存预热标记。"""
    order, redis = patch_common(monkeypatch)
    patch_factory(monkeypatch)

    result = dialog_agent_preheat.run(
        "session",
        {"name": "患者"},
        {"scale_codes": ["scale"], "engine_type": "text"},
    )

    assert result == {
        "status": "preheated",
        "session_id": "session",
        "engine_type": "text",
        "question_count": 1,
    }
    assert order == ["runtime"]
    redis.get.assert_called_once()


def test_dialog_preheat_rejects_voice_engine(monkeypatch):
    """第一期文本闭环应拒绝语音引擎。"""
    patch_common(monkeypatch)
    _deps, _agent, factory = patch_factory(monkeypatch)

    result = dialog_agent_preheat.run(
        "session",
        {},
        {"scale_codes": ["scale"], "engine_type": "doubao"},
    )

    assert result == {"status": "failed", "reason": "unknown_engine_type"}
    factory.assert_not_called()


def test_dialog_preheat_rejects_unknown_engine_type(monkeypatch):
    """未知引擎类型应返回稳定失败原因且不调用工厂。"""
    patch_common(monkeypatch)
    _deps, _agent, factory = patch_factory(monkeypatch)

    result = dialog_agent_preheat.run(
        "session",
        {},
        {"scale_codes": ["scale"], "engine_type": "unknown"},
    )

    assert result == {"status": "failed", "reason": "unknown_engine_type"}
    factory.assert_not_called()


def test_dialog_preheat_reports_no_questions(monkeypatch):
    """未加载到问题应返回 no_questions_loaded。"""
    patch_common(monkeypatch, questions=[])
    patch_factory(monkeypatch)

    result = dialog_agent_preheat.run(
        "session",
        {},
        {"scale_codes": ["scale"], "engine_type": "text"},
    )

    assert result == {"status": "failed", "reason": "no_questions_loaded"}


def test_dialog_preheat_retries_unhandled_failure(monkeypatch):
    """未处理异常必须交给 Celery retry。"""
    import app.celery_app.runtime as runtime_module

    monkeypatch.setattr(
        runtime_module,
        "ensure_worker_runtime",
        Mock(side_effect=RuntimeError("runtime failed")),
    )
    retry = Mock(side_effect=RuntimeError("retry scheduled"))
    monkeypatch.setattr(dialog_agent_preheat, "retry", retry)

    with pytest.raises(RuntimeError, match="retry scheduled"):
        dialog_agent_preheat.run(
            "session",
            {},
            {"scale_codes": ["scale"]},
        )

    assert retry.call_args.kwargs["countdown"] == 5
    assert retry.call_args.kwargs["max_retries"] == 3


class _FakeScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeReconcileDb:
    def __init__(self, *, session, latest_ai_turn, latest_patient):
        self.session = session
        self.latest_ai_turn = latest_ai_turn
        self.latest_patient = latest_patient
        self.scalar_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalars(self, _statement):
        return _FakeScalarRows([self.session])

    def scalar(self, _statement):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.latest_ai_turn
        if self.scalar_calls == 2:
            return self.latest_patient
        if self.scalar_calls == 3:
            # dispatch_answer_workers 内部查询 source message 类型。
            return self.latest_patient.message_type
        raise AssertionError("unexpected scalar call")


def _patch_reconcile_dependencies(
    monkeypatch,
    *,
    latest_patient,
    voice_active=False,
):
    import app.celery_app.runtime as runtime_module
    import app.models.base as base_module
    import app.services.agent_dispatch_service as dispatch_module
    import app.utils.redis_client as redis_module
    from app.celery_app import tasks as task_module

    session = SimpleNamespace(
        id=1,
        session_no="SESS-VOICE",
        session_status="active",
        deleted=0,
    )
    db = _FakeReconcileDb(
        session=session,
        latest_ai_turn=1,
        latest_patient=latest_patient,
    )
    redis = SimpleNamespace(
        get=Mock(return_value={"active": True} if voice_active else None),
    )
    dialog_delay = Mock()
    schedule_delay = Mock()
    extraction_delay = Mock()
    opening_dispatch = Mock()

    monkeypatch.setattr(runtime_module, "ensure_worker_runtime", lambda: None)
    monkeypatch.setattr(base_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(redis_module, "get_redis", lambda: redis)
    monkeypatch.setattr(
        dispatch_module,
        "build_session_agent_payload",
        lambda _db, _session: (
            {"name": "患者"},
            {"task_id": 1, "scale_codes": ["scale"]},
        ),
    )
    monkeypatch.setattr(dispatch_module, "dispatch_opening_workers", opening_dispatch)
    monkeypatch.setattr(task_module.dialog_agent_worker, "delay", dialog_delay)
    monkeypatch.setattr(task_module.schedule_agent_worker, "delay", schedule_delay)
    monkeypatch.setattr(task_module.extraction_agent_worker, "delay", extraction_delay)
    return dialog_delay, schedule_delay, extraction_delay, opening_dispatch, redis


def test_reconcile_voice_patient_message_never_generates_text_dialog(monkeypatch):
    """语音患者消息必须始终由 Qwen Realtime 回复，补偿任务不能生成第二条文字回复。"""
    latest_patient = SimpleNamespace(
        turn_no=2,
        message_no="MSG-PATIENT-VOICE-2",
        message_type="语音",
    )
    dialog, schedule, extraction, opening, _redis = _patch_reconcile_dependencies(
        monkeypatch,
        latest_patient=latest_patient,
        voice_active=False,
    )

    reconcile_pending_dialog_turns.run()

    dialog.assert_not_called()
    schedule.assert_not_called()
    extraction.assert_not_called()
    opening.assert_not_called()


def test_reconcile_text_turn_does_not_generate_dialog_while_voice_active(monkeypatch):
    """Qwen Realtime 活跃期间，即使最后一条是文本也不能并发生成文本 Dialog 回复。"""
    latest_patient = SimpleNamespace(
        turn_no=2,
        message_no="MSG-PATIENT-TEXT-2",
        message_type="文本",
    )
    dialog, schedule, extraction, opening, redis = _patch_reconcile_dependencies(
        monkeypatch,
        latest_patient=latest_patient,
        voice_active=True,
    )

    reconcile_pending_dialog_turns.run()

    assert redis.get.called
    dialog.assert_not_called()
    schedule.assert_not_called()
    extraction.assert_not_called()
    opening.assert_not_called()


def test_reconcile_keeps_text_compensation_when_voice_is_inactive(monkeypatch):
    """普通文字会话仍需保留原有补偿能力。"""
    latest_patient = SimpleNamespace(
        turn_no=2,
        message_no="MSG-PATIENT-TEXT-2",
        message_type="文本",
    )
    dialog, schedule, extraction, opening, _redis = _patch_reconcile_dependencies(
        monkeypatch,
        latest_patient=latest_patient,
        voice_active=False,
    )

    result = reconcile_pending_dialog_turns.run()

    assert result["dispatched"] == 1
    dialog.assert_called_once()
    schedule.assert_called_once()
    extraction.assert_called_once()
    opening.assert_not_called()
