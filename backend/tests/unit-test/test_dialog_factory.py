"""Dialog Agent SDK 工厂（agents/factory.py）单元测试。

覆盖：
  - text 模式解析 agent_models 语言绑定并构造 TextChatEngine；
  - doubao 模式解析语音绑定并构造 DoubaoVoiceEngine；
  - 未知 engine_type / 未绑定模型 / 缺少 api_base 的错误路径；
  - middlewares / state_store / history_store 依赖注入透传。
"""

import pytest

import medagent.agents.factory as factory_module
from medagent.agents.factory import create_dialog_agent
from medagent.agents.service_agent.dialog_agent.engine import (
    DoubaoVoiceEngine,
    TextChatEngine,
)
from medagent.configs.agent_config import AgentConfig
from medagent.configs.model_config import ModelConfig, ModelType


def build_config() -> AgentConfig:
    return AgentConfig(
        models=[
            ModelConfig(
                name="qwen-plus",
                type=ModelType.LANGUAGE,
                model="qwen-plus",
                api_base="https://example.com/v1",
                api_key="lang-key",
                timeout=600.0,
            ),
            ModelConfig(
                name="dialog_agent_voice",
                type=ModelType.VOICE,
                model="doubao-voice-v1",
                websocket_url="wss://voice.example/ws",
                api_key="voice-key",
                timeout=60.0,
            ),
        ],
        agent_models={
            "dialog_agent": {"language": "qwen-plus", "voice": "dialog_agent_voice"},
        },
    )


@pytest.fixture
def patched_config(monkeypatch):
    """替换工厂内部 get_agent_config 返回测试配置。"""
    config = build_config()
    monkeypatch.setattr(factory_module, "get_agent_config", lambda: config)
    return config


def question_list():
    return []


def test_create_dialog_agent_text_builds_text_engine(patched_config):
    agent = create_dialog_agent(
        session_id="s1",
        patient_info={"name": "患者"},
        task_list=question_list(),
        engine_type="text",
        agent_name="dialog_agent",
    )
    assert isinstance(agent.engine, TextChatEngine)
    assert agent.engine.model == "qwen-plus"
    assert agent.session_id == "s1"


def test_create_dialog_agent_doubao_builds_voice_engine(patched_config):
    agent = create_dialog_agent(
        session_id="s2",
        patient_info={},
        task_list=question_list(),
        engine_type="doubao",
        agent_name="dialog_agent",
    )
    assert isinstance(agent.engine, DoubaoVoiceEngine)
    assert agent.engine.ws_url == "wss://voice.example/ws"


def test_create_dialog_agent_rejects_unknown_engine_type(patched_config):
    with pytest.raises(ValueError, match="不支持的 engine_type"):
        create_dialog_agent(
            session_id="s3",
            patient_info={},
            task_list=question_list(),
            engine_type="bogus",
        )


def test_create_dialog_agent_text_requires_language_binding(monkeypatch):
    config = AgentConfig(
        models=[
            ModelConfig(
                name="only-voice",
                type=ModelType.VOICE,
                model="v",
                websocket_url="wss://x/ws",
                api_key="k",
            ),
        ],
        agent_models={"dialog_agent": {"voice": "only-voice"}},
    )
    monkeypatch.setattr(factory_module, "get_agent_config", lambda: config)

    with pytest.raises(ValueError, match="未绑定语言模型"):
        create_dialog_agent(
            session_id="s4",
            patient_info={},
            task_list=question_list(),
            engine_type="text",
        )


def test_create_dialog_agent_text_requires_api_base(monkeypatch):
    config = AgentConfig(
        models=[
            ModelConfig(
                name="no-base",
                type=ModelType.LANGUAGE,
                model="m",
                api_key="k",
            ),
        ],
        agent_models={"dialog_agent": {"language": "no-base"}},
    )
    monkeypatch.setattr(factory_module, "get_agent_config", lambda: config)

    with pytest.raises(ValueError, match="缺少 api_base"):
        create_dialog_agent(
            session_id="s5",
            patient_info={},
            task_list=question_list(),
            engine_type="text",
        )


def test_create_dialog_agent_injects_dependencies(patched_config):
    sentinel_mw = object()
    state_store = object()
    history_store = object()
    agent = create_dialog_agent(
        session_id="s6",
        patient_info={},
        task_list=question_list(),
        engine_type="text",
        middlewares=[sentinel_mw],
        state_store=state_store,
        history_store=history_store,
    )
    assert agent.state_store is state_store
    assert agent.history_store is history_store
    assert sentinel_mw in agent.middleware.middlewares
