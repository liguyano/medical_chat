"""模型配置 Schema
作用：定义 medagent SDK 内部使用的统一模型配置模型，覆盖 OpenAI 兼容语言模型
      与豆包实时语音模型；通过 `type` 字段区分模型类别，供工厂按类别装配引擎。
说明：
  - 本模块只依赖 pydantic，不导入 app.*，符合 App/Agent 分离约定；
  - 密钥支持 `$ENV` / `${ENV}` 环境变量引用，运行时解析，避免明文入库；
  - `extra="allow"` 允许 config.yaml 追加供应商特有字段（如 temperature、max_tokens），
    统一透传给底层客户端构造函数。
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ModelType(str, Enum):
    """模型类别枚举
    作用：区分同一 models 列表中的不同模型用途，供工厂按类别选择装配方式。
    """

    LANGUAGE = "language"  # OpenAI 兼容语言模型（文本对话 / 抽取 / 排程）
    VOICE = "voice"        # 实时语音模型（豆包 WebSocket 协议）


def _resolve_env_ref(raw: str, *, owner: str) -> str:
    """解析环境变量引用
    作用：将 `$VAR` 或 `${VAR}` 形式解析为环境变量真实值；非引用则原样返回。
    Args:
        - raw: 原始字符串（可能是明文或环境变量引用）
        - owner: 归属名称（用于报错定位，如模型名）
    Return:
        - 解析后的真实值
    """
    if not raw.startswith("$"):
        return raw
    variable = raw[1:]
    if variable.startswith("{") and variable.endswith("}"):
        variable = variable[1:-1]
    value = os.getenv(variable)
    if not value:
        raise RuntimeError(f"模型 {owner} 缺少环境变量: {variable}")
    return value


class ModelConfig(BaseModel):
    """统一模型配置
    作用：描述一个可被智能体引用的模型；同时兼容语言模型与语音模型两类字段。
    类参数：
        - name: 模型唯一标识（供 agent_models 绑定引用）
        - type: 模型类别（language / voice）
        - use: 底层客户端类路径或工厂标识（如 openai:AsyncOpenAI）
        - model: 供应商侧模型名称（如 qwen-plus / doubao-voice-v1）
        - api_key: 密钥（支持 $ENV 引用）
        - api_base: OpenAI 兼容端点（语言模型必填）
        - websocket_url: 实时语音 WebSocket 端点（语音模型必填）
        - 其余为可选元数据与供应商特有字段（extra 透传）
    """

    # 允许 config.yaml 追加供应商特有字段（temperature / max_tokens / voice 等）
    model_config = ConfigDict(extra="allow")

    # ---- 核心标识 ----
    name: str
    type: ModelType = ModelType.LANGUAGE
    display_name: str | None = None
    use: str = "openai:AsyncOpenAI"
    model: str

    # ---- 通用凭据 ----
    api_key: str = ""
    timeout: float = 600.0
    max_retries: int = 2

    # ---- 语言模型（OpenAI 兼容）字段 ----
    api_base: str | None = None
    enable_prompt_caching: bool = False
    prompt_cache_ttl: str | None = None
    supports_thinking: bool = False
    supports_vision: bool = False
    supports_reasoning_effort: bool = False
    when_thinking_enabled: dict[str, Any] | None = None
    when_thinking_disabled: dict[str, Any] | None = None
    context_window: int | None = None

    # ---- 语音模型（豆包 WebSocket）字段 ----
    websocket_url: str | None = None
    voice: str | None = None
    audio_format: str | None = None
    reconnect_attempts: int | None = None

    def resolved_api_key(self) -> str:
        """解析密钥
        作用：将 `$ENV` / `${ENV}` 引用解析为真实密钥值。
        Return:
            - 真实密钥字符串
        """
        return _resolve_env_ref(self.api_key, owner=self.name)

    def extra_settings(self) -> dict[str, Any]:
        """提取供应商特有字段
        作用：返回 config.yaml 中额外声明、未被显式建模的字段（如 temperature），
              供工厂透传给底层客户端构造函数。
        Return:
            - 额外字段字典（不含 None 值）
        """
        extra = getattr(self, "model_extra", None) or {}
        return {key: value for key, value in extra.items() if value is not None}
