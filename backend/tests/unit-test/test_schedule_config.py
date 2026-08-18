"""Schedule Agent 模型配置单元测试。"""

from pathlib import Path

import pytest

from app.configs.app_config import AppConfig, ModelConfig


def make_model(api_key: str = "plain-key") -> ModelConfig:
    """创建最小 OpenAI 兼容模型配置。"""
    return ModelConfig(
        name="qwen-plus",
        display_name="Qwen Plus",
        use="openai:AsyncOpenAI",
        model="qwen-plus",
        api_base="https://example.com/v1",
        api_key=api_key,
    )


def test_agent_binding_resolves_model():
    """智能体绑定应解析到对应模型配置。"""
    config = AppConfig(
        models=[make_model()],
        agent_models={"schedule_agent": "qwen-plus"},
    )
    assert config.get_agent_model_config("schedule_agent").model == "qwen-plus"


def test_unknown_agent_binding_returns_none():
    """未配置智能体不应静默选择其他模型。"""
    assert AppConfig(models=[make_model()]).get_agent_model_config("unknown") is None


def test_literal_api_key_is_returned_unchanged():
    """非环境变量密钥可以直接使用。"""
    assert make_model().resolved_api_key() == "plain-key"


def test_environment_api_key_is_resolved(monkeypatch):
    """$ENV 形式必须从运行环境解析。"""
    monkeypatch.setenv("TEST_LLM_KEY", "resolved-key")
    assert make_model("$TEST_LLM_KEY").resolved_api_key() == "resolved-key"
    assert make_model("${TEST_LLM_KEY}").resolved_api_key() == "resolved-key"


def test_missing_environment_api_key_raises(monkeypatch):
    """缺失密钥必须在创建客户端前给出明确错误。"""
    monkeypatch.delenv("MISSING_LLM_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MISSING_LLM_KEY"):
        make_model("$MISSING_LLM_KEY").resolved_api_key()


def test_extended_model_fields_follow_requested_yaml_shape():
    """模型配置应接受思考、视觉和缓存能力字段。"""
    model = ModelConfig(
        **{
            **make_model().model_dump(),
            "enable_prompt_caching": True,
            "prompt_cache_ttl": "5m",
            "supports_thinking": True,
            "supports_vision": True,
            "supports_reasoning_effort": True,
            "when_thinking_enabled": {"extra_body": {"thinking": {"type": "enabled"}}},
        }
    )
    assert model.enable_prompt_caching is True
    assert model.when_thinking_enabled["extra_body"]["thinking"]["type"] == "enabled"


def test_config_example_resolves_schedule_agent_binding(monkeypatch):
    """仓库配置模板必须能被真实配置加载器解析。"""
    config_path = Path(__file__).resolve().parents[3] / "config.example.yaml"
    monkeypatch.setenv("MEDICAL_CONFIG", str(config_path))
    config = AppConfig()
    model = config.get_agent_model_config("schedule_agent")
    assert model is not None
    assert model.name == "qwen-plus-precise"
    assert model.api_base.endswith("/compatible-mode/v1")
