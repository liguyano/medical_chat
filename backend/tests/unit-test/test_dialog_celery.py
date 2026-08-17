"""Dialog Agent Celery 预热任务单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.celery_app.tasks import dialog_agent_preheat
from app.configs.app_config import ModelConfig, VoiceModelConfig


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


def text_config():
    return ModelConfig(
        name="text-model",
        display_name="Text",
        model="text-model",
        api_base="https://example.com/v1",
        api_key="text-key",
    )


def voice_config():
    return VoiceModelConfig(
        name="dialog_agent",
        model="voice-model",
        websocket_url="wss://voice.example/ws",
        api_key="voice-key",
        timeout=30,
    )


def patch_common(monkeypatch, *, config, questions=None):
    """替换 Celery 任务的应用层依赖。"""
    import app.celery_app.runtime as runtime_module
    import app.configs.app_config as config_module
    import app.managers.assessment_loader as loader_module
    import app.utils.redis_client as redis_module

    order = []
    monkeypatch.setattr(
        runtime_module,
        "ensure_worker_runtime",
        lambda: order.append("runtime"),
    )
    loader = SimpleNamespace(
        load_questions_by_scale_codes=AsyncMock(
            side_effect=lambda _: order.append("loader") or (questions or [question()])
        )
    )
    monkeypatch.setattr(loader_module, "AssessmentQuestionLoader", lambda: loader)
    monkeypatch.setattr(config_module, "get_app_config", lambda: config)
    redis = object()
    monkeypatch.setattr(redis_module, "get_redis", lambda: redis)
    return order, loader, redis


def test_dialog_preheat_rejects_missing_scale_codes():
    """缺少量表编码时应快速失败且不初始化外部依赖。"""
    result = dialog_agent_preheat.run("session", {}, {})

    assert result == {"status": "failed", "reason": "missing_scale_codes"}


def test_dialog_preheat_builds_text_engine_and_app_agent(monkeypatch):
    """text 模式应使用 Agent 文本模型绑定和 App builder。"""
    import medagent.agents.service_agent.dialog_agent as dialog_module

    import app.workers.dialog_agent_runtime as runtime_module

    config = SimpleNamespace(
        get_agent_model_config=lambda _: text_config(),
        get_voice_model_config=lambda _: None,
    )
    order, loader, redis = patch_common(monkeypatch, config=config)
    text_engine = object()
    text_factory = Mock(return_value=text_engine)
    monkeypatch.setattr(dialog_module, "TextChatEngine", text_factory)
    agent = SimpleNamespace(initialize=AsyncMock())
    builder = Mock(return_value=agent)
    monkeypatch.setattr(runtime_module, "build_dialog_agent", builder)

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
    text_factory.assert_called_once_with(
        api_key="text-key",
        model="text-model",
        api_base="https://example.com/v1",
        timeout=600.0,
    )
    builder.assert_called_once()
    assert builder.call_args.kwargs["engine"] is text_engine
    assert builder.call_args.kwargs["redis_client"] is redis
    agent.initialize.assert_awaited_once_with()
    loader.load_questions_by_scale_codes.assert_awaited_once_with(["scale"])


def test_dialog_preheat_builds_voice_engine(monkeypatch):
    """doubao 模式应使用独立 voice_models 配置。"""
    import medagent.agents.service_agent.dialog_agent as dialog_module

    import app.workers.dialog_agent_runtime as runtime_module

    config = SimpleNamespace(
        get_agent_model_config=lambda _: None,
        get_voice_model_config=lambda _: voice_config(),
    )
    patch_common(monkeypatch, config=config)
    voice_engine = object()
    voice_factory = Mock(return_value=voice_engine)
    monkeypatch.setattr(dialog_module, "DoubaoVoiceEngine", voice_factory)
    agent = SimpleNamespace(initialize=AsyncMock())
    monkeypatch.setattr(
        runtime_module,
        "build_dialog_agent",
        Mock(return_value=agent),
    )

    result = dialog_agent_preheat.run(
        "session",
        {},
        {"scale_codes": ["scale"], "engine_type": "doubao"},
    )

    assert result["status"] == "preheated"
    voice_factory.assert_called_once_with(
        api_key="voice-key",
        model="voice-model",
        ws_url="wss://voice.example/ws",
        timeout=30.0,
    )


@pytest.mark.parametrize(
    ("config", "engine_type", "reason"),
    [
        (
            SimpleNamespace(
                get_voice_model_config=lambda _: None,
                get_agent_model_config=lambda _: None,
            ),
            "doubao",
            "missing_llm_config",
        ),
        (
            SimpleNamespace(
                get_voice_model_config=lambda _: None,
                get_agent_model_config=lambda _: None,
            ),
            "text",
            "missing_llm_config",
        ),
        (
            SimpleNamespace(
                get_voice_model_config=lambda _: voice_config(),
                get_agent_model_config=lambda _: text_config(),
            ),
            "unknown",
            "unknown_engine_type",
        ),
    ],
)
def test_dialog_preheat_reports_configuration_errors(
    monkeypatch,
    config,
    engine_type,
    reason,
):
    """模型缺失和未知引擎类型应返回稳定失败原因。"""
    patch_common(monkeypatch, config=config)

    result = dialog_agent_preheat.run(
        "session",
        {},
        {"scale_codes": ["scale"], "engine_type": engine_type},
    )

    assert result == {"status": "failed", "reason": reason}


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
