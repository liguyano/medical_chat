"""Agent 工厂：组装完整 Agent 实例
作用：提供统一的 agent 实例化入口，遵循纯参数设计，封装引擎创建与依赖注入。
说明：
  - create_dialog_agent()：config 驱动，需按 engine_type 在文本/语音双引擎间选择，
    因此内部解析 agent_models 绑定并装配引擎；
  - create_schedule_agent() / create_extraction_agent()：纯依赖注入，单一
    BaseChatModel 由应用层显式传入（最易测试），不在工厂内读取全局配置；
  - 两类签名的有意不对称源于 Dialog 的双引擎特性，非疏漏；
  - 依赖注入模式：middlewares / state_store / history_store / tool_executor 由应用层传入。
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from medagent.agents.middlewares.base import DialogMiddleware
from medagent.agents.service_agent.dialog_agent.agent import DialogAgent
from medagent.agents.service_agent.dialog_agent.engine import (
    DialogEngine,
    TextChatEngine,
)
from medagent.agents.service_agent.dialog_agent.models import (
    DialogHistoryStore,
    DialogStateStore,
    DialogTextDeltaSink,
    DialogToolExecutor,
)
from medagent.agents.service_agent.dialog_agent.tools import execute_tool
from medagent.agents.service_agent.extraction_agent import FieldExtractionAgent
from medagent.agents.service_agent.schedule_agent import ScheduleAgent
from medagent.agents.service_agent.schedule_agent.models import QuestionTask
from medagent.configs import get_agent_config
from medagent.configs.model_config import ModelType
from medagent.providers import create_voice_engine

__all__ = [
    "create_dialog_agent",
    "create_extraction_agent",
    "create_schedule_agent",
]


def create_dialog_agent(
    *,
    session_id: str,
    patient_info: dict[str, Any],
    task_list: list[QuestionTask],
    engine_type: str = "text",
    agent_name: str = "dialog_agent",
    middlewares: list[DialogMiddleware] | None = None,
    state_store: DialogStateStore | None = None,
    history_store: DialogHistoryStore | None = None,
    tool_executor: DialogToolExecutor = execute_tool,
    text_delta_sink: DialogTextDeltaSink | None = None,
) -> DialogAgent:
    """创建 Dialog Agent（SDK 工厂入口）
    作用：根据 engine_type 从 agent_models 绑定解析模型，装配对应引擎并组装 Dialog Agent。
    Args:
        - session_id: 会话 ID
        - patient_info: 患者信息字典
        - task_list: 量表任务列表（QuestionTask 对象）
        - engine_type: 引擎类型（"text" 文本对话 / "doubao" 豆包实时语音）
        - agent_name: 智能体名称（用于从 agent_models 解析模型绑定，默认 dialog_agent）
        - middlewares: 中间件列表（应用层注入）
        - state_store: 状态存储协议实例（应用层注入）
        - history_store: 历史存储协议实例（应用层注入）
        - tool_executor: 工具执行器（默认使用 SDK 内置 execute_tool）
    Return:
        - DialogAgent 实例
    Raises:
        - ValueError: engine_type 不支持 / 智能体未绑定模型 / 模型缺少必要字段
    """
    engine: DialogEngine
    config = get_agent_config()

    if engine_type == "text":
        # 文本引擎：从 agent_models 解析语言模型绑定
        model_config = config.get_agent_model_config(agent_name, ModelType.LANGUAGE)
        if not model_config:
            raise ValueError(
                f"智能体 {agent_name} 未绑定语言模型（engine_type='text' 需要 language 绑定）"
            )

        # 提取 TextChatEngine 构造参数
        if not model_config.api_base:
            raise ValueError(
                f"语言模型 {model_config.name} 缺少 api_base 配置，"
                "TextChatEngine 需要 OpenAI 兼容 endpoint"
            )

        engine = TextChatEngine(
            api_key=model_config.resolved_api_key(),
            model=model_config.model,
            api_base=model_config.api_base,
            timeout=model_config.timeout,
            max_retries=model_config.max_retries,
            request_options=model_config.chat_completion_options(),
        )

    elif engine_type == "doubao":
        # 语音引擎：从 agent_models 解析语音模型绑定
        model_config = config.get_agent_model_config(agent_name, ModelType.VOICE)
        if not model_config:
            raise ValueError(
                f"智能体 {agent_name} 未绑定语音模型（engine_type='doubao' 需要 voice 绑定）"
            )

        engine = create_voice_engine(model_config)

    else:
        raise ValueError(
            f"不支持的 engine_type: {engine_type}，仅支持 'text' 或 'doubao'"
        )

    # 组装 Dialog Agent（依赖注入模式）
    return DialogAgent(
        session_id=session_id,
        patient_info=patient_info,
        task_list=task_list,
        engine=engine,
        middlewares=middlewares or [],
        state_store=state_store,
        history_store=history_store,
        tool_executor=tool_executor,
        text_delta_sink=text_delta_sink,
    )


def create_schedule_agent(
    *,
    session_id: str,
    task_list: list[QuestionTask],
    model: BaseChatModel,
    check_interval: int = 5,
) -> ScheduleAgent:
    """创建 Schedule Agent（SDK 工厂入口）
    作用：以纯依赖注入方式组装调度智能体，模型由应用层显式传入。
    Args:
        - session_id: 会话 ID
        - task_list: 量表问题任务列表（QuestionTask 对象）
        - model: LangChain BaseChatModel（应用层用 create_chat_model 构造后注入）
        - check_interval: 每隔多少轮执行一次检查
    Return:
        - ScheduleAgent 实例
    """
    return ScheduleAgent(
        session_id=session_id,
        task_list=task_list,
        model=model,
        check_interval=check_interval,
    )


def create_extraction_agent(
    *,
    session_id: str,
    scale_codes: list[str],
    model: BaseChatModel,
) -> FieldExtractionAgent:
    """创建 Field Extraction Agent（SDK 工厂入口）
    作用：以纯依赖注入方式组装字段抽取智能体，模型由应用层显式传入。
    Args:
        - session_id: 会话 ID
        - scale_codes: 量表编码列表
        - model: LangChain BaseChatModel（应用层用 create_chat_model 构造后注入）
    Return:
        - FieldExtractionAgent 实例
    """
    return FieldExtractionAgent(
        session_id=session_id,
        scale_codes=scale_codes,
        model=model,
    )
