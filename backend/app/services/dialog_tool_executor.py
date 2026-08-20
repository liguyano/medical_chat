"""应用层 Dialog 工具执行器
作用：让宣教工具读取 Demo 配置中心数据库，其余工具继续复用 medagent SDK。
"""

from __future__ import annotations

from typing import Any

from medagent.agents.service_agent.dialog_agent.tools import (
    execute_tool as execute_sdk_tool,
)

from app.models import base as model_base
from app.services.system_config_service import get_education_tool_result


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """执行应用层 Dialog 工具。"""
    if tool_name != "get_education_material":
        return await execute_sdk_tool(tool_name, arguments)
    if model_base.SessionLocal is None:
        raise RuntimeError("数据库未初始化")
    category = str(arguments.get("category") or "")
    level = int(arguments.get("level") or 2)
    with model_base.SessionLocal() as db:
        return get_education_tool_result(
            db,
            category=category,
            level=level,
        )
