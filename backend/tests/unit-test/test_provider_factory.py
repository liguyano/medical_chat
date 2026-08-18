"""模型工厂（providers/llm_model.py）单元测试。

覆盖：
  - create_chat_model 类型校验 / base_url 规整 / extra 透传 / thinking 转换；
  - create_voice_engine 类型校验 / websocket_url 校验 / 显式字段应用与默认保留。
"""

import pytest
from langchain_openai import ChatOpenAI
from medagent.configs.model_config import ModelConfig, ModelType
from medagent.providers import create_chat_model, create_voice_engine


def language_model(**overrides) -> ModelConfig:
    base = {
        "name": "qwen-plus",
        "type": ModelType.LANGUAGE,
        "model": "qwen-plus",
        "api_base": "https://example.com/v1",
        "api_key": "plain-key",
        "timeout": 600.0,
        "max_retries": 2,
    }
    base.update(overrides)
    return ModelConfig(**base)


def voice_model(**overrides) -> ModelConfig:
    base = {
        "name": "dialog_agent_voice",
        "type": ModelType.VOICE,
        "model": "doubao-voice-v1",
        "websocket_url": "wss://voice.example/ws",
        "api_key": "voice-key",
        "timeout": 60.0,
    }
    base.update(overrides)
    return ModelConfig(**base)


# ---------------- create_chat_model ----------------


def test_create_chat_model_returns_chatopenai():
    model = create_chat_model(language_model())
    assert isinstance(model, ChatOpenAI)


def test_create_chat_model_rejects_voice_type():
    with pytest.raises(ValueError, match="仅支持 type=language"):
        create_chat_model(voice_model())


def test_create_chat_model_maps_api_base_to_base_url():
    model = create_chat_model(language_model(api_base="https://custom.host/v1"))
    # ChatOpenAI 将 base_url 存为 openai_api_base
    assert str(model.openai_api_base) == "https://custom.host/v1"


def test_create_chat_model_passes_extra_fields():
    model = create_chat_model(
        language_model(temperature=0.3, max_tokens=1234)
    )
    assert model.temperature == 0.3
    assert model.max_tokens == 1234
    assert model.extra_body["enable_thinking"] is False


def test_create_chat_model_passes_thinking_mode_to_extra_body():
    model = create_chat_model(language_model(enable_thinking=True))

    assert model.extra_body["enable_thinking"] is True


# ---------------- create_voice_engine ----------------


def test_create_voice_engine_rejects_language_type():
    with pytest.raises(ValueError, match="仅支持 type=voice"):
        create_voice_engine(language_model())


def test_create_voice_engine_requires_websocket_url():
    mc = voice_model()
    # 强制清空 websocket_url
    mc.websocket_url = None
    with pytest.raises(ValueError, match="缺少 websocket_url"):
        create_voice_engine(mc)


def test_create_voice_engine_applies_configured_fields():
    mc = voice_model(reconnect_attempts=3, voice="zh_female_qingxin", audio_format="pcm")
    engine = create_voice_engine(mc)
    assert engine.reconnect_attempts == 3
    assert engine.voice == "zh_female_qingxin"
    assert engine.audio_format == "pcm"
    assert engine.ws_url == "wss://voice.example/ws"


def test_create_voice_engine_keeps_defaults_when_unset():
    engine = create_voice_engine(voice_model())
    assert engine.reconnect_attempts == 1
    assert engine.voice == "zh-CN-YunxiNeural"
    assert engine.audio_format == "pcm"
