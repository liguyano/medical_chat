"""Dialog Agent 线程状态 Schema
作用：定义 Dialog Agent 在 LangGraph 中的状态结构，扩展基础 AgentState，
      适配 deerflow-style 设计。
说明：
  - 当前简化实现：不引入 deerflow 的 sandbox/artifacts/todos/goal/promoted/delegations/
    skill_context/summary_text 等扩展字段；
  - 仅保留 Dialog Agent 核心业务状态：messages + dialog_metadata；
  - 未来若需支持更丰富的 LangGraph 能力（如工具搜索/子智能体委派），可参考 deerflow
    ThreadState 扩展。
"""
from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState
from langchain_core.messages import AnyMessage

__all__ = ["DialogThreadState"]


class DialogMetadata(TypedDict):
    """Dialog Agent 元数据
    作用：存储对话会话级别的辅助信息。
    类参数：
        - session_id: 对话会话 ID（与 Redis Stream key 对应）
        - assessment_instance_id: 当前评估实例 ID（可选）
    """

    session_id: NotRequired[str | None]
    assessment_instance_id: NotRequired[int | None]


def merge_dialog_metadata(
    existing: DialogMetadata | None, new: DialogMetadata | None
) -> DialogMetadata | None:
    """Reducer for dialog_metadata
    作用：合并元数据字典，新值覆盖旧值；new 为 None 时保留 existing。
    Args:
        - existing: 现有元数据
        - new: 新元数据
    Return:
        - 合并后的元数据
    """
    if new is None:
        return existing
    if existing is None:
        return new
    return {**existing, **new}


class DialogThreadState(AgentState):
    """Dialog Agent 线程状态
    作用：LangGraph 状态 Schema，继承 AgentState（自带 messages 通道 + add_messages reducer）。
    类参数：
        - messages: 消息列表（继承自 AgentState，默认使用 add_messages reducer）
        - dialog_metadata: Dialog Agent 元数据（自定义 reducer）
    """

    dialog_metadata: Annotated[DialogMetadata | None, merge_dialog_metadata]
