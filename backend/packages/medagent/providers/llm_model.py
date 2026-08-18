"""模型工厂：纯参数构造 BaseChatModel 与语音引擎
作用：根据 ModelConfig 实例化语言模型（LangChain BaseChatModel）或语音引擎
      （DoubaoVoiceEngine），供 agent 工厂复用；不直接读取全局配置，遵循纯参数设计。
说明：
  - create_chat_model() 返回 langchain_core.language_models.BaseChatModel，
    对接 LangGraph create_agent；
  - create_voice_engine() 返回 DoubaoVoiceEngine（WebSocket 全双工，无法适配 BaseChatModel）；
  - 参考 deerflow factory.py 的 resolve_class / model_dump / thinking 转换 / 默认值注入模式；
  - 不依赖 app.*，只导入 medagent.* 与第三方库。
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from medagent.agents.service_agent.dialog_agent.engine import DoubaoVoiceEngine
from medagent.configs.model_config import ModelConfig, ModelType

logger = logging.getLogger(__name__)

__all__ = ["create_chat_model", "create_voice_engine"]


def _normalize_openai_base_url(settings: dict[str, Any], model_config: ModelConfig) -> None:
    """规整 OpenAI base_url
    作用：将 ModelConfig.api_base 映射为 ChatOpenAI 构造参数 base_url。
    Args:
        - settings: 待传给 ChatOpenAI 的参数字典（原地修改）
        - model_config: 源模型配置
    """
    if model_config.api_base:
        settings["base_url"] = model_config.api_base
        settings.pop("api_base", None)


def _apply_stream_chunk_timeout_default(settings: dict[str, Any]) -> None:
    """注入流式超时默认值
    作用：为 ChatOpenAI 流式响应设置 240s 兜底超时，避免流中断时死等。
    Args:
        - settings: 待传给 ChatOpenAI 的参数字典（原地修改）
    说明：stream_chunk_timeout 是 langchain-openai>=1.5 的有效字段。
    """
    if "timeout" in settings and "stream_chunk_timeout" not in settings:
        settings.setdefault("stream_chunk_timeout", 240.0)


def _apply_thinking_transforms(
    settings: dict[str, Any], model_config: ModelConfig
) -> None:
    """应用 thinking 模式转换
    作用：根据 model_config.when_thinking_enabled / when_thinking_disabled 深度合并参数。
    Args:
        - settings: 待传给 ChatOpenAI 的参数字典（原地修改）
        - model_config: 源模型配置
    说明：
      - 当前简化实现：仅当 settings 中存在 "thinking" 键时，选择 enabled/disabled 字典进行合并；
      - 未来若需更精细的 deep merge（嵌套字典递归合并），可参考 deerflow 的 _deep_merge 实现。
    """
    thinking_enabled = settings.get("thinking", False)
    transform = (
        model_config.when_thinking_enabled
        if thinking_enabled
        else model_config.when_thinking_disabled
    )
    if transform:
        settings.update(transform)


def _warn_unknown_model_settings(settings: dict[str, Any], model_config: ModelConfig) -> None:
    """警告未识别的模型配置字段
    作用：检测 extra_settings 中不在 ChatOpenAI 已知参数列表内的字段，提示可能的拼写错误。
    Args:
        - settings: 最终传给 ChatOpenAI 的参数字典
        - model_config: 源模型配置
    """
    known_params = {
        "model",
        "base_url",
        "api_key",
        "timeout",
        "max_retries",
        "temperature",
        "max_tokens",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "stream_chunk_timeout",
        "thinking",
        "model_kwargs",
        "extra_body",
    }
    extra = model_config.extra_settings()
    unknown = set(extra.keys()) - known_params
    if unknown:
        logger.warning(
            f"模型 {model_config.name} 包含未识别的配置字段（可能拼写错误）: {unknown}"
        )


def create_chat_model(model_config: ModelConfig) -> BaseChatModel:
    """创建 LangChain BaseChatModel 实例
    作用：根据 ModelConfig 实例化语言模型，供 LangGraph create_agent 使用。
    Args:
        - model_config: 语言模型配置（type 必须为 ModelType.LANGUAGE）
    Return:
        - BaseChatModel 实例（当前固定返回 ChatOpenAI）
    """
    if model_config.type != ModelType.LANGUAGE:
        raise ValueError(
            f"create_chat_model 仅支持 type=language 的模型，"
            f"当前模型 {model_config.name} 类别为 {model_config.type.value}"
        )

    # 基础参数：model / api_key / timeout / max_retries
    settings: dict[str, Any] = {
        "model": model_config.model,
        "api_key": model_config.resolved_api_key(),
        "timeout": model_config.timeout,
        "max_retries": model_config.max_retries,
    }

    # 透传供应商特有字段，并显式关闭 qwen3.5 的思考模式，避免结构化结果被推理 token 截断。
    settings.update(model_config.chat_completion_options())

    # 规整 api_base → base_url
    _normalize_openai_base_url(settings, model_config)

    # 注入流式超时默认值
    _apply_stream_chunk_timeout_default(settings)

    # 应用 thinking 模式转换
    _apply_thinking_transforms(settings, model_config)

    # 警告未识别字段
    _warn_unknown_model_settings(settings, model_config)

    # 当前固定使用 ChatOpenAI；未来若需支持其他供应商，可参考 deerflow resolve_class 动态加载
    logger.info(
        "[LLM] 创建真实语言模型客户端: agent_model=%s, model=%s, api_base=%s, "
        "temperature=%s, max_tokens=%s, enable_thinking=%s",
        model_config.name,
        model_config.model,
        model_config.api_base,
        settings.get("temperature"),
        settings.get("max_tokens") or settings.get("max_completion_tokens"),
        settings.get("extra_body", {}).get("enable_thinking"),
    )
    return ChatOpenAI(**settings)


def create_voice_engine(model_config: ModelConfig) -> DoubaoVoiceEngine:
    """创建豆包实时语音引擎
    作用：根据 ModelConfig 实例化 DoubaoVoiceEngine（WebSocket 全双工协议）。
    Args:
        - model_config: 语音模型配置（type 必须为 ModelType.VOICE）
    Return:
        - DoubaoVoiceEngine 实例
    """
    if model_config.type != ModelType.VOICE:
        raise ValueError(
            f"create_voice_engine 仅支持 type=voice 的模型，"
            f"当前模型 {model_config.name} 类别为 {model_config.type.value}"
        )

    if not model_config.websocket_url:
        raise ValueError(
            f"语音模型 {model_config.name} 缺少 websocket_url 配置，无法创建 DoubaoVoiceEngine"
        )

    # 基础参数（voice / audio_format / reconnect_attempts 为 ModelConfig 显式建模字段，
    # 不在 extra_settings 中，需直接从字段读取）
    kwargs: dict[str, Any] = {
        "api_key": model_config.resolved_api_key(),
        "model": model_config.model,
        "ws_url": model_config.websocket_url,
        "timeout": model_config.timeout,
    }
    # reconnect_attempts 是构造参数，配置为空时沿用引擎默认值
    if model_config.reconnect_attempts is not None:
        kwargs["reconnect_attempts"] = model_config.reconnect_attempts

    engine = DoubaoVoiceEngine(**kwargs)

    # voice / audio_format 非构造参数，构造后覆盖实例属性（配置为空则保留引擎默认）
    if model_config.voice:
        engine.voice = model_config.voice
    if model_config.audio_format:
        engine.audio_format = model_config.audio_format

    return engine
