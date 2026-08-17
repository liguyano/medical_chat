"""Dialog Agent 工具定义
作用：用 LangChain @tool 装饰器定义宣教/知情同意等工具，函数签名即 schema 单一来源；
      对引擎侧导出 OpenAI function dict（DIALOG_TOOLS），对编排层导出执行入口（execute_tool）。
说明（对齐 deerflow tools/builtins 的 LangChain 工具形态）：
  - @tool 定义：函数签名 + docstring 自动生成参数 schema，消除 schema 与实现漂移；
  - 引擎（DoubaoVoiceEngine / TextChatEngine）需 OpenAI function dict，故经
    convert_to_openai_tool 从 @tool 生成，不再手写 dict；
  - execute_tool 改为注册表查表 + ainvoke，删除手写 if/elif 路由。
"""
import logging
from typing import Any, Literal
from uuid import uuid4

from langchain_core.tools import BaseTool, tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError

logger = logging.getLogger(__name__)


# ==================== 工具定义（@tool，签名即 schema） ====================


@tool
async def get_education_material(
    category: Literal["tobacco", "alcohol", "diabetes", "allergy"],
    level: int = 2,
) -> dict[str, Any]:
    """获取健康宣教材料（抽烟、饮酒、糖尿病、药物过敏等）。

    Args:
        category: 宣教类别（tobacco=抽烟, alcohol=饮酒, diabetes=糖尿病, allergy=药物过敏）。
        level: 宣教级别（1=简短提醒, 2=标准宣教, 3=深度宣教）。
    """
    if category not in {"tobacco", "alcohol", "diabetes", "allergy"}:
        return {"success": False, "message": f"不支持的宣教类别: {category}"}
    if level not in {1, 2, 3}:
        return {"success": False, "message": "宣教级别必须是 1、2 或 3"}
    logger.info("[Tool] get_education_material: category=%s, level=%s", category, level)

    # TODO: 从 interaction_rule 表查询宣教规则（批次B）
    # TODO: 从 education 表查询宣教内容（批次B）

    # 当前返回结构化占位
    category_map = {
        "tobacco": "抽烟",
        "alcohol": "饮酒",
        "diabetes": "糖尿病",
        "allergy": "药物过敏",
    }
    return {
        "success": True,
        "placeholder": True,
        "material_id": f"edu_{category}_{level}",
        "category": category,
        "level": level,
        "title": f"{category_map.get(category, category)}健康宣教",
        "content": f"【占位内容】这是关于{category_map.get(category, category)}的{level}级宣教材料。批次B落地后从数据库读取。",
        "audio_url": None,
        "note": "TODO: 批次B实现 education 表后替换为真实内容",
    }


@tool
async def trigger_consent_form(
    form_type: Literal["surgery", "anesthesia", "blood_transfusion", "tobacco"],
) -> dict[str, Any]:
    """触发知情同意书签署流程（手术、麻醉、输血等）。

    Args:
        form_type: 知情同意书类型（surgery=手术, anesthesia=麻醉,
            blood_transfusion=输血, tobacco=戒烟）。
    """
    if form_type not in {"surgery", "anesthesia", "blood_transfusion", "tobacco"}:
        return {"success": False, "message": f"不支持的知情同意书类型: {form_type}"}
    logger.info("[Tool] trigger_consent_form: form_type=%s", form_type)

    # TODO: 发布 consent_form 事件到 Redis Stream（批次B）
    # TODO: 从 consent_form 表查询表单模板（批次B）

    # 当前返回结构化占位
    form_type_map = {
        "surgery": "手术",
        "anesthesia": "麻醉",
        "blood_transfusion": "输血",
        "tobacco": "戒烟",
    }
    return {
        "success": True,
        "placeholder": True,
        "form_id": f"consent_{form_type}_{uuid4().hex}",
        "form_type": form_type,
        "title": f"{form_type_map.get(form_type, form_type)}知情同意书",
        "status": "pending_signature",
        "note": "TODO: 批次B实现 consent_form 表与签名流程后完善",
    }


@tool
async def play_audio(audio_url: str) -> dict[str, Any]:
    """播放音频（预留工具，当前未实现）。

    Args:
        audio_url: 音频文件 URL。
    """
    logger.info("[Tool] play_audio: audio_url=%s", audio_url)
    return {
        "success": False,
        "message": "play_audio 工具预留，当前未实现",
    }


# ==================== 工具注册表 ====================

# LangChain BaseTool 注册表（名称 → 工具对象），供执行路由与 schema 生成复用
_TOOL_OBJECTS: list[BaseTool] = [
    get_education_material,
    trigger_consent_form,
    play_audio,
]
_TOOL_REGISTRY: dict[str, BaseTool] = {t.name: t for t in _TOOL_OBJECTS}


def build_openai_tool_schemas() -> list[dict[str, Any]]:
    """构建 OpenAI function 调用 schema 列表
    作用：从 @tool 对象生成引擎侧所需的 OpenAI function dict，保证 schema 与实现单一来源。
    Return:
        - OpenAI function dict 列表
    """
    return [convert_to_openai_tool(t) for t in _TOOL_OBJECTS]


# 引擎侧使用的 OpenAI function dict 列表（对外名保持 DIALOG_TOOLS 不变）
DIALOG_TOOLS: list[dict[str, Any]] = build_openai_tool_schemas()


# ==================== 工具执行路由器 ====================


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """工具执行路由器
    作用：按名称从注册表查表并 ainvoke，替代手写 if/elif 路由。
    Args:
        - tool_name: 工具名称
        - arguments: 工具参数
    Return:
        - 工具执行结果（工具函数返回值）
    """
    target = _TOOL_REGISTRY.get(tool_name)
    if target is None:
        logger.warning("[Tool] 未知工具: %s", tool_name)
        return {"success": False, "message": f"未知工具: {tool_name}"}
    try:
        return await target.ainvoke(arguments)
    except (TypeError, ValueError, ValidationError):
        logger.exception("[Tool] 参数错误: %s", tool_name)
        return {"success": False, "message": f"工具参数错误: {tool_name}"}
