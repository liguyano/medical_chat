"""应用层 Dialog 工具执行器
作用：让宣教工具读取 Demo 配置中心数据库，其余工具继续复用 medagent SDK。
"""

from __future__ import annotations

from typing import Any

from medagent.agents.service_agent.dialog_agent.tools import (
    execute_tool as execute_sdk_tool,
)


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """执行应用层 Dialog 工具。健康宣教入口已停用。"""
    if tool_name == "get_education_material":
        return {
            "success": False,
            "disabled": True,
            "message": "健康宣教工具已停用",
        }
    return await execute_sdk_tool(tool_name, arguments)
