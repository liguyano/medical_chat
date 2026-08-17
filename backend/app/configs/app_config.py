"""应用配置加载模块
作用：从根目录 config.yaml 加载配置，支持环境变量覆盖，提供全局单例访问。
说明：
  - 遵循 AGENTS.md 约定，导入路径为 `app.configs.app_config`；
  - 使用 pydantic-settings 做类型校验与多来源合并；
  - 来源优先级（高→低）：初始化参数 > 环境变量(APP_*) > config.yaml > 默认值；
  - 环境变量前缀 APP_，嵌套用双下划线，例如 APP_DATABASE__PASSWORD。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# ==================== 子配置模型 ====================

class AppInfo(BaseModel):
    """应用基础配置"""
    name: str = "medical-evaluate"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True


class DatabaseConfig(BaseModel):
    """PostgreSQL 数据库配置"""
    host: str = "localhost"
    port: int = 15432
    user: str = "medical"
    password: str = "medical_dev_password"
    db: str = "medical_evaluate"
    pool_size: int = 10
    max_overflow: int = 20
    pool_pre_ping: bool = True
    echo: bool = False

    @property
    def url(self) -> str:
        """同步连接串（psycopg2）"""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @property
    def async_url(self) -> str:
        """异步连接串（asyncpg）"""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RedisConfig(BaseModel):
    """Redis 配置（缓存 / Stream / Celery）"""
    host: str = "localhost"
    port: int = 6379
    cache_db: int = 0
    broker_db: int = 1
    backend_db: int = 2
    password: str | None = None
    stream_maxlen: int = 10000

    def url(self, db: int) -> str:
        """按库号拼装 Redis 连接串
        Args:
            - db: 目标库号
        Return:
            - Redis URL 字符串
        """
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{db}"

    @property
    def cache_url(self) -> str:
        return self.url(self.cache_db)


class CeleryConfig(BaseModel):
    """Celery 配置"""
    broker_url: str | None = None
    backend_url: str | None = None
    task_time_limit: int = 1800
    task_soft_time_limit: int = 1500


class LoggingConfig(BaseModel):
    """日志系统配置"""
    level: str = "INFO"
    # 使用别名 json 对应 YAML 键，避免与 BaseModel.json 属性冲突
    json_format: bool = Field(default=False, alias="json")
    file: str | None = None

    model_config = {"populate_by_name": True}


class ModelConfig(BaseModel):
    """OpenAI 兼容文本模型配置。"""

    model_config = ConfigDict(extra="allow")

    name: str
    display_name: str
    use: str = "openai:AsyncOpenAI"
    model: str
    api_base: str
    api_key: str
    timeout: float = 600.0
    max_retries: int = 2
    enable_prompt_caching: bool = False
    prompt_cache_ttl: str | None = None
    supports_thinking: bool = False
    supports_vision: bool = False
    supports_reasoning_effort: bool = False
    when_thinking_enabled: dict[str, Any] | None = None
    when_thinking_disabled: dict[str, Any] | None = None

    def resolved_api_key(self) -> str:
        """解析 `$ENV` 或 `${ENV}` 形式的密钥引用。"""
        if not self.api_key.startswith("$"):
            return self.api_key
        variable = self.api_key[1:]
        if variable.startswith("{") and variable.endswith("}"):
            variable = variable[1:-1]
        value = os.getenv(variable)
        if not value:
            raise RuntimeError(f"模型 {self.name} 缺少环境变量: {variable}")
        return value


class VoiceModelConfig(BaseModel):
    """非 OpenAI 协议的实时语音模型配置。"""

    name: str
    model: str
    websocket_url: str
    api_key: str
    timeout: float = 60.0
    max_retries: int = 2

    def resolved_api_key(self) -> str:
        """解析实时语音模型的环境变量密钥引用。"""
        if not self.api_key.startswith("$"):
            return self.api_key
        variable = self.api_key[1:]
        if variable.startswith("{") and variable.endswith("}"):
            variable = variable[1:-1]
        value = os.getenv(variable)
        if not value:
            raise RuntimeError(f"语音模型 {self.name} 缺少环境变量: {variable}")
        return value


# ==================== YAML 配置来源 ====================

def _find_config_file() -> Path | None:
    """定位根目录 config.yaml
    作用：从当前文件向上回溯寻找 config.yaml；
          支持 MEDICAL_CONFIG 环境变量显式指定路径。
    Return:
        - 存在则返回 Path，否则 None
    """
    explicit = os.getenv("MEDICAL_CONFIG")
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config.yaml"
        if candidate.is_file():
            return candidate
    return None


class _YamlSettingsSource(PydanticBaseSettingsSource):
    """YAML 配置来源
    作用：作为 pydantic-settings 的自定义来源，读取 config.yaml。
          其优先级低于环境变量，从而实现环境变量覆盖 YAML。
    """

    def get_field_value(self, field, field_name):
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = _find_config_file()
        if path is None:
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


# ==================== 顶层配置 ====================

class AppConfig(BaseSettings):
    """应用顶层配置
    作用：聚合所有子配置，从 YAML 与环境变量加载。
    """
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: str = "development"
    app: AppInfo = Field(default_factory=AppInfo)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    models: list[ModelConfig] = Field(default_factory=list)
    agent_models: dict[str, str] = Field(default_factory=dict)
    voice_models: list[VoiceModelConfig] = Field(default_factory=list)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """自定义来源优先级
        作用：init > env > yaml > 默认值。
        """
        return (
            init_settings,
            env_settings,
            _YamlSettingsSource(settings_cls),
        )

    def resolved_celery_broker_url(self) -> str:
        """解析 Celery broker URL（未显式配置时用 redis.broker_db 拼装）"""
        return self.celery.broker_url or self.redis.url(self.redis.broker_db)

    def resolved_celery_backend_url(self) -> str:
        """解析 Celery backend URL（未显式配置时用 redis.backend_db 拼装）"""
        return self.celery.backend_url or self.redis.url(self.redis.backend_db)

    def get_model_config(self, name: str) -> ModelConfig | None:
        """按模型名称获取 OpenAI 兼容模型配置。"""
        return next((model for model in self.models if model.name == name), None)

    def get_agent_model_config(self, agent_name: str) -> ModelConfig | None:
        """获取指定智能体绑定的模型配置
        Args:
            - agent_name: 智能体名称，例如 schedule_agent
        Return:
            - 模型配置；未绑定或模型不存在时返回 None
        """
        model_name = self.agent_models.get(agent_name)
        return self.get_model_config(model_name) if model_name else None

    def get_voice_model_config(self, name: str) -> VoiceModelConfig | None:
        """按名称获取非 OpenAI 协议的实时语音模型配置。"""
        return next((model for model in self.voice_models if model.name == name), None)


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    """获取全局应用配置单例
    作用：加载配置并缓存，多来源合并由 pydantic-settings 完成。
    Return:
        - AppConfig 实例
    """
    return AppConfig()
