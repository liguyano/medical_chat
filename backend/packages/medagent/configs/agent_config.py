"""Agent 配置 Schema
作用：聚合 medagent SDK 运行所需的模型注册表与「智能体 → 模型」绑定关系，
      实现「先注册模型、再为智能体指定模型」的配置模式，避免硬编码。
说明：
  - 只依赖 pydantic 与本包 model_config，不导入 app.*；
  - agent_models 支持两种绑定写法：
      1) 简写：schedule_agent: qwen-plus              （单模型，默认按类别取用）
      2) 详写：dialog_agent: {language: qwen-plus, voice: doubao-voice}
    以覆盖 dialog_agent 需要同时绑定语言模型（文本降级）与语音模型的场景。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from medagent.configs.model_config import ModelConfig, ModelType


class AgentModelBinding(BaseModel):
    """智能体模型绑定
    作用：描述单个智能体引用的模型名称，可分别指定语言模型与语音模型。
    类参数：
        - language: 语言模型 name（对应 models 列表中 type=language 的项）
        - voice: 语音模型 name（对应 models 列表中 type=voice 的项，可空）
    """

    language: str | None = None
    voice: str | None = None


class AgentConfig(BaseModel):
    """Agent 配置根模型
    作用：持有全部模型注册表 models 与智能体绑定 agent_models，提供按名称、
          按智能体、按类别的查询能力。
    类参数：
        - models: 已注册的模型配置列表（语言 + 语音统一登记）
        - agent_models: 智能体到模型的绑定（值可为字符串简写或 AgentModelBinding）
    """

    models: list[ModelConfig] = Field(default_factory=list)
    agent_models: dict[str, str | AgentModelBinding] = Field(default_factory=dict)

    def get_model_config(self, name: str) -> ModelConfig | None:
        """按模型名称获取配置
        Args:
            - name: 模型 name
        Return:
            - ModelConfig；不存在时 None
        """
        return next((m for m in self.models if m.name == name), None)

    def _binding(self, agent_name: str) -> AgentModelBinding | None:
        """规整智能体绑定
        作用：将字符串简写或详写统一为 AgentModelBinding；简写视为语言模型绑定。
        Args:
            - agent_name: 智能体名称
        Return:
            - AgentModelBinding；未绑定时 None
        """
        raw = self.agent_models.get(agent_name)
        if raw is None:
            return None
        if isinstance(raw, AgentModelBinding):
            return raw
        # 字符串简写：默认作为语言模型绑定
        return AgentModelBinding(language=raw)

    def get_agent_model_config(
        self, agent_name: str, model_type: ModelType = ModelType.LANGUAGE
    ) -> ModelConfig | None:
        """获取智能体绑定的指定类别模型配置
        Args:
            - agent_name: 智能体名称（如 dialog_agent）
            - model_type: 期望的模型类别（language / voice）
        Return:
            - ModelConfig；未绑定或模型不存在时 None
        """
        binding = self._binding(agent_name)
        if binding is None:
            return None
        model_name = binding.voice if model_type == ModelType.VOICE else binding.language
        if not model_name:
            return None
        model = self.get_model_config(model_name)
        # 类别校验：绑定的模型类别需与请求一致，避免语音端点误用为语言模型
        if model is not None and model.type != model_type:
            raise ValueError(
                f"智能体 {agent_name} 绑定的模型 {model_name} 类别为 {model.type.value}，"
                f"与请求类别 {model_type.value} 不符"
            )
        return model
