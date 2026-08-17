"""Dialog Agent 工具定义
作用：定义宣教材料获取、知情同意书触发等工具 schema 和执行器（桩实现）。
"""
import logging
from typing import Any, Literal
from uuid import uuid4

logger = logging.getLogger(__name__)


# ==================== 工具 Schema 定义 ====================

TOOL_GET_EDUCATION_MATERIAL = {
    "type": "function",
    "function": {
        "name": "get_education_material",
        "description": "获取健康宣教材料（抽烟、饮酒、糖尿病、药物过敏等）",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["tobacco", "alcohol", "diabetes", "allergy"],
                    "description": "宣教类别：tobacco=抽烟, alcohol=饮酒, diabetes=糖尿病, allergy=药物过敏",
                },
                "level": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                    "description": "宣教级别：1=简短提醒, 2=标准宣教, 3=深度宣教",
                },
            },
            "required": ["category"],
        },
    },
}

TOOL_TRIGGER_CONSENT_FORM = {
    "type": "function",
    "function": {
        "name": "trigger_consent_form",
        "description": "触发知情同意书签署流程（手术、麻醉、输血等）",
        "parameters": {
            "type": "object",
            "properties": {
                "form_type": {
                    "type": "string",
                    "enum": ["surgery", "anesthesia", "blood_transfusion", "tobacco"],
                    "description": "知情同意书类型：surgery=手术, anesthesia=麻醉, blood_transfusion=输血, tobacco=戒烟",
                },
            },
            "required": ["form_type"],
        },
    },
}

TOOL_PLAY_AUDIO = {
    "type": "function",
    "function": {
        "name": "play_audio",
        "description": "播放音频（预留工具，当前未实现）",
        "parameters": {
            "type": "object",
            "properties": {
                "audio_url": {
                    "type": "string",
                    "description": "音频文件 URL",
                },
            },
            "required": ["audio_url"],
        },
    },
}


# ==================== 工具注册表 ====================

DIALOG_TOOLS = [
    TOOL_GET_EDUCATION_MATERIAL,
    TOOL_TRIGGER_CONSENT_FORM,
    TOOL_PLAY_AUDIO,
]


# ==================== 工具执行器（桩实现） ====================


async def execute_get_education_material(
    category: Literal["tobacco", "alcohol", "diabetes", "allergy"],
    level: int = 2,
) -> dict[str, Any]:
    """获取健康宣教材料（桩实现）
    作用：优先从 interaction_rule 表读规则；批次B education 表未落地则返回占位。
    Args:
        - category: 宣教类别
        - level: 宣教级别（1-3）
    Return:
        - 宣教材料结构化数据
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


async def execute_trigger_consent_form(
    form_type: Literal["surgery", "anesthesia", "blood_transfusion", "tobacco"],
) -> dict[str, Any]:
    """触发知情同意书签署流程（桩实现）
    作用：发布 consent_form 事件到 Redis Stream，返回占位 form_id。
    Args:
        - form_type: 知情同意书类型
    Return:
        - 触发结果（含占位 form_id）
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


async def execute_play_audio(audio_url: str) -> dict[str, Any]:
    """播放音频（预留工具）
    Args:
        - audio_url: 音频 URL
    Return:
        - 播放结果
    """
    logger.info("[Tool] play_audio: audio_url=%s", audio_url)
    return {
        "success": False,
        "message": "play_audio 工具预留，当前未实现",
    }


# ==================== 工具路由器 ====================


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """工具执行路由器
    作用：根据 tool_name 分发到具体执行器。
    Args:
        - tool_name: 工具名称
        - arguments: 工具参数
    Return:
        - 工具执行结果
    """
    try:
        if tool_name == "get_education_material":
            return await execute_get_education_material(**arguments)
        if tool_name == "trigger_consent_form":
            return await execute_trigger_consent_form(**arguments)
        if tool_name == "play_audio":
            return await execute_play_audio(**arguments)
    except TypeError:
        logger.exception("[Tool] 参数错误: %s", tool_name)
        return {"success": False, "message": f"工具参数错误: {tool_name}"}
    logger.warning("[Tool] 未知工具: %s", tool_name)
    return {"success": False, "message": f"未知工具: {tool_name}"}
