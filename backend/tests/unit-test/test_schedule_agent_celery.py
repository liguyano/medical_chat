"""Schedule Agent Celery 任务组装单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.celery_app.tasks import schedule_agent_worker
from app.configs.app_config import ModelConfig


def model_config():
    """创建任务测试模型配置。"""
    return ModelConfig(
        name="qwen-plus",
        display_name="Qwen Plus",
        model="qwen-plus",
        api_base="https://example.com/v1",
        api_key="key",
    )


def test_worker_reports_missing_model_binding(monkeypatch):
    """未绑定模型时任务应返回明确失败原因。"""
    import app.configs.app_config as config_module

    monkeypatch.setattr(
        config_module,
        "get_app_config",
        lambda: SimpleNamespace(get_agent_model_config=lambda _: None),
    )
    result = schedule_agent_worker.run(
        "session",
        {"scale_codes": ["adl"]},
    )
    assert result == {"status": "failed", "reason": "llm_not_configured"}


def test_worker_builds_runner_with_chat_model(monkeypatch):
    """任务应用 create_chat_model 构造 BaseChatModel 并注入运行器。"""
    import medagent.providers as providers_module

    import app.celery_app.runtime as runtime_module
    import app.configs.app_config as config_module
    import app.utils.redis_client as redis_module
    import app.workers.schedule_agent_runner as runner_module

    config = model_config()
    monkeypatch.setattr(
        config_module,
        "get_app_config",
        lambda: SimpleNamespace(get_agent_model_config=lambda _: config),
    )
    fake_model = object()
    model_factory = Mock(return_value=fake_model)
    monkeypatch.setattr(providers_module, "create_chat_model", model_factory)
    runtime_initializer = Mock()
    monkeypatch.setattr(runtime_module, "ensure_worker_runtime", runtime_initializer)
    monkeypatch.setattr(redis_module, "get_redis", lambda: object())

    fake_runner = SimpleNamespace(
        run=AsyncMock(return_value={"status": "completed", "turns": 5})
    )
    runner_factory = Mock(return_value=fake_runner)
    monkeypatch.setattr(runner_module, "ScheduleAgentRunner", runner_factory)

    result = schedule_agent_worker.run(
        "session",
        {"scale_codes": ["adl"], "check_interval": 5},
    )

    assert result == {"status": "completed", "turns": 5}
    model_factory.assert_called_once_with(config)
    assert runner_factory.call_args.kwargs["model"] is fake_model
    runtime_initializer.assert_called_once_with()
    fake_runner.run.assert_awaited_once_with(
        "session",
        scale_codes=["adl"],
        check_interval=5,
    )


def test_worker_retries_unhandled_failure(monkeypatch):
    """运行器异常必须交给 Celery 重试。"""
    import medagent.providers as providers_module

    import app.celery_app.runtime as runtime_module
    import app.configs.app_config as config_module
    import app.utils.redis_client as redis_module
    import app.workers.schedule_agent_runner as runner_module

    config = model_config()
    monkeypatch.setattr(
        config_module,
        "get_app_config",
        lambda: SimpleNamespace(get_agent_model_config=lambda _: config),
    )
    monkeypatch.setattr(providers_module, "create_chat_model", lambda _: object())
    monkeypatch.setattr(runtime_module, "ensure_worker_runtime", Mock())
    monkeypatch.setattr(redis_module, "get_redis", lambda: object())
    monkeypatch.setattr(
        runner_module,
        "ScheduleAgentRunner",
        Mock(side_effect=RuntimeError("runner failed")),
    )
    retry = Mock(side_effect=RuntimeError("retry scheduled"))
    monkeypatch.setattr(schedule_agent_worker, "retry", retry)

    with pytest.raises(RuntimeError, match="retry scheduled"):
        schedule_agent_worker.run("session", {"scale_codes": ["adl"]})
    assert retry.call_args.kwargs["countdown"] == 10
    assert retry.call_args.kwargs["max_retries"] == 3
