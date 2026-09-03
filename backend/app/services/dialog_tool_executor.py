"""应用层 Dialog 工具执行器
作用：转发 Dialog Agent 的工具调用；宣教工具已从当前对话工具列表移除。
"""

from __future__ import annotations

from typing import Any

from medagent.agents.service_agent.dialog_agent.tools import (
    execute_tool as execute_sdk_tool,
)

async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """执行应用层 Dialog 工具。"""
    return await execute_sdk_tool(tool_name, arguments)
