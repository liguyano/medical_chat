"""Dialog Agent Celery 预热任务单元测试。

重构后：Celery 任务不再直接构造引擎，而是委托 SDK 工厂 create_dialog_agent，
并从 get_runtime_dependencies 注入 middlewares / state_store / history_store。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.celery_app.tasks import dialog_agent_preheat


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
    """替换 Celery 任务的应用层依赖（runtime / loader）。"""
    import app.celery_app.runtime as runtime_module
    import app.managers.assessment_loader as loader_module

    order = []
    monkeypatch.setattr(
        runtime_module,
        "ensure_worker_runtime",
        lambda: order.append("runtime"),
    )
    # 区分 None（默认单题）与 []（显式无题）
    result_questions = [question()] if questions is None else questions
    loader = SimpleNamespace(
        load_questions_by_scale_codes=AsyncMock(
            side_effect=lambda _: order.append("loader") or result_questions
        )
    )
    monkeypatch.setattr(loader_module, "AssessmentQuestionLoader", lambda: loader)
    return order, loader


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
    """text 模式应委托 SDK 工厂并注入运行时依赖。"""
    order, loader = patch_common(monkeypatch)
    deps, agent, factory = patch_factory(monkeypatch)

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
    assert order == ["runtime", "loader"]
    factory.assert_called_once()
    kwargs = factory.call_args.kwargs
    assert kwargs["engine_type"] == "text"
    assert kwargs["agent_name"] == "dialog_agent"
    assert kwargs["session_id"] == "session"
    assert kwargs["patient_info"] == {"name": "患者"}
    assert kwargs["middlewares"] is deps["middlewares"]
    assert kwargs["state_store"] is deps["state_store"]
    assert kwargs["history_store"] is deps["history_store"]
    agent.initialize.assert_awaited_once_with()
    loader.load_questions_by_scale_codes.assert_awaited_once_with(["scale"])


def test_dialog_preheat_voice_engine_uses_factory(monkeypatch):
    """doubao 模式应委托 SDK 工厂并传递 engine_type=doubao。"""
    patch_common(monkeypatch)
    _deps, agent, factory = patch_factory(monkeypatch)

    result = dialog_agent_preheat.run(
        "session",
        {},
        {"scale_codes": ["scale"], "engine_type": "doubao"},
    )

    assert result["status"] == "preheated"
    assert result["engine_type"] == "doubao"
    kwargs = factory.call_args.kwargs
    assert kwargs["engine_type"] == "doubao"
    assert kwargs["agent_name"] == "dialog_agent"
    agent.initialize.assert_awaited_once_with()


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
