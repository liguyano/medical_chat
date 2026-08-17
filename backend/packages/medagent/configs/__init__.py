"""medagent 配置层
作用：作为 medagent SDK 的配置入口，独立加载根目录 config.yaml 的 models 与
      agent_models，构建 AgentConfig 单例；不依赖 app.* 配置层，保证 SDK 自洽。
说明：
  - 定位 config.yaml 的策略与 app 层一致：优先 MEDICAL_CONFIG 环境变量，否则从
    当前文件向上回溯查找根目录 config.yaml；
  - 仅提取 models / agent_models 两段，其余（database/redis/celery）由 app 层负责；
  - 使用 lru_cache 缓存，避免重复读盘。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from medagent.configs.agent_config import AgentConfig, AgentModelBinding
from medagent.configs.model_config import ModelConfig, ModelType

__all__ = [
    "AgentConfig",
    "AgentModelBinding",
    "ModelConfig",
    "ModelType",
    "get_agent_config",
    "load_agent_config",
]


def _find_config_file() -> Path | None:
    """定位根目录 config.yaml
    作用：优先读取 MEDICAL_CONFIG 环境变量指定的路径；否则从本文件向上回溯查找。
    Return:
        - 存在则返回 Path，否则 None
    """
    explicit = os.getenv("MEDICAL_CONFIG")
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_agent_config(path: str | os.PathLike[str] | None = None) -> AgentConfig:
    """加载 Agent 配置
    作用：读取 config.yaml 的 models / agent_models，构建 AgentConfig。
    Args:
        - path: 显式配置文件路径；为空则自动定位
    Return:
        - AgentConfig 实例
    """
    config_file = Path(path) if path else _find_config_file()
    if config_file is None or not config_file.is_file():
        raise FileNotFoundError("未找到 config.yaml，无法加载 medagent 模型配置")

    with open(config_file, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return AgentConfig(
        models=raw.get("models", []),
        agent_models=raw.get("agent_models", {}),
    )


@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    """获取全局 Agent 配置单例
    作用：加载并缓存 AgentConfig，供工厂与 provider 复用。
    Return:
        - AgentConfig 实例
    """
    return load_agent_config()
