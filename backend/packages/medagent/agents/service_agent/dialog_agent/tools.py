"""Dialog Agent 工具定义
作用：用 LangChain @tool 装饰器定义宣教、知情同意与呼叫医护工具，函数签名即 schema 单一来源；
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

_EDUCATION_MATERIALS: dict[str, dict[str, Any]] = {
    "tobacco": {
        "title": "住院期间戒烟与烟草危害宣教",
        "original_content": (
            "吸烟会增加心脑血管疾病、呼吸系统疾病、伤口愈合不良和感染的风险。"
            "住院病区属于无烟环境，请勿在病房、卫生间、楼梯间等区域吸烟。"
            "如出现明显烦躁、失眠、头痛或强烈吸烟冲动，请告知医护人员，"
            "由医护人员评估是否需要进一步的戒烟支持。"
        ),
        "patient_content": (
            "住院期间请先不要吸烟，也不要在病房、卫生间或楼梯间吸烟。"
            "如果烟瘾明显、心里烦躁或睡不好，可以直接告诉护士，我们会协助您。"
        ),
        "spoken_content": (
            "跟您提醒一下，住院期间请先不要吸烟，病房、卫生间和楼梯间也都是无烟区域。"
            "如果烟瘾明显，或者出现烦躁、睡不好等不舒服，请及时告诉护士。"
        ),
        "priority": "medium",
        "source_name": "住院期间戒烟与烟草危害宣教（系统内置版）",
    },
    "alcohol": {
        "title": "饮酒风险与住院安全宣教",
        "original_content": (
            "饮酒可能影响血压、血糖、睡眠、肝功能以及部分药物的疗效和不良反应。"
            "住院期间请勿自行饮酒。长期大量饮酒者突然停止饮酒后，如出现手抖、"
            "明显出汗、心慌、烦躁、幻觉或抽搐，应立即告知医护人员。"
        ),
        "patient_content": (
            "住院期间请不要自行饮酒，因为酒精可能和药物相互影响。"
            "如果您平时饮酒较多，停酒后出现手抖、出汗、心慌、烦躁或看见异常事物，"
            "请马上呼叫护士。"
        ),
        "spoken_content": (
            "住院期间请不要自行饮酒，以免影响用药和身体恢复。"
            "如果停酒后出现手抖、出汗、心慌、烦躁或其他明显不适，请马上告诉护士。"
        ),
        "priority": "high",
        "source_name": "饮酒风险与住院安全宣教（系统内置版）",
    },
    "diabetes": {
        "title": "糖尿病住院期间安全宣教",
        "original_content": (
            "糖尿病患者住院期间应按医护安排监测血糖、用药和进餐，不得自行增减胰岛素"
            "或降糖药。出现心慌、手抖、出汗、明显饥饿、头晕、乏力或意识改变时，"
            "可能为低血糖，应立即告知医护人员；出现持续口渴、多尿、恶心呕吐、"
            "呼吸异常或意识改变时也应及时求助。"
        ),
        "patient_content": (
            "请按护士安排测血糖、吃饭和用药，不要自己增减胰岛素或降糖药。"
            "如果出现心慌、手抖、出汗、很饿、头晕，或持续口渴、恶心呕吐，"
            "请立即呼叫护士。"
        ),
        "spoken_content": (
            "住院期间请按安排测血糖、吃饭和用药，不要自行调整降糖药。"
            "如果出现心慌、手抖、出汗、很饿、头晕，或者持续口渴、恶心呕吐，"
            "请马上呼叫护士。"
        ),
        "priority": "high",
        "source_name": "糖尿病住院期间安全宣教（系统内置版）",
    },
    "allergy": {
        "title": "药物过敏安全宣教",
        "original_content": (
            "已知或疑似药物过敏者，应向每次接诊的医生、护士和药师主动说明具体药物名称"
            "及既往反应。不得自行再次试用可疑药物。用药后如出现全身皮疹、面唇舌肿胀、"
            "喉头发紧、呼吸困难、胸闷、头晕或意识改变，应立即停止自行活动并呼叫医护人员。"
        ),
        "patient_content": (
            "以后每次看病、检查或用药前，请主动告诉医生和护士您对什么药过敏、"
            "当时出现过什么反应，不要自行再试这种药。若用药后出现呼吸困难、"
            "喉咙发紧、脸或嘴唇肿、全身皮疹，请立即呼叫医护人员。"
        ),
        "spoken_content": (
            "请记住，以后每次就医和用药前，都要主动告诉医生和护士具体对什么药过敏，"
            "以及当时出现过什么反应。若用药后出现呼吸困难、喉咙发紧、脸或嘴唇肿，"
            "请立即呼叫医护人员。"
        ),
        "priority": "high",
        "source_name": "药物过敏安全宣教（系统内置版）",
    },
}

_CONSENT_DOCUMENTS: dict[str, dict[str, Any]] = {
    "admission_nursing": {
        "title": "AI 辅助入院护理评估知情确认",
        "document_version": "AI-ADMISSION-1.0",
        "clauses": [
            {
                "clause_code": "AI_SCOPE",
                "clause_name": "AI 服务范围",
                "patient_content": (
                    "本次对话由 AI 护理助手协助收集入院护理信息，AI 不替代医生诊断、"
                    "护士判断或现场处置，整理结果将由护士复核。"
                ),
                "importance_level": "critical",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            },
            {
                "clause_code": "DATA_USE",
                "clause_name": "信息使用与复核",
                "patient_content": (
                    "您提供的信息用于本次住院护理评估、风险识别和护理安排；"
                    "如发现记录不准确，您可以随时更正或要求护士人工处理。"
                ),
                "importance_level": "important",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            },
            {
                "clause_code": "EMERGENCY",
                "clause_name": "紧急情况处理",
                "patient_content": (
                    "如出现呼吸困难、胸痛、意识改变、大量出血或其他紧急不适，"
                    "请立即使用呼叫铃或直接联系医护人员，不要等待 AI 对话处理。"
                ),
                "importance_level": "critical",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            },
        ],
    },
    "surgery": {
        "title": "手术知情同意提醒",
        "document_version": "SURGERY-REMINDER-1.0",
        "clauses": [
            {
                "clause_code": "SURGERY_EXPLANATION",
                "clause_name": "术式与风险需由医生解释",
                "patient_content": (
                    "具体手术方式、替代方案、主要风险和预期获益必须由主管医生结合病情说明。"
                    "如仍有疑问，请先呼叫医护人员，充分理解后再签署正式手术知情同意书。"
                ),
                "importance_level": "critical",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            }
        ],
    },
    "anesthesia": {
        "title": "麻醉知情同意提醒",
        "document_version": "ANESTHESIA-REMINDER-1.0",
        "clauses": [
            {
                "clause_code": "ANESTHESIA_EXPLANATION",
                "clause_name": "麻醉方案与风险需由麻醉医生解释",
                "patient_content": (
                    "麻醉方式、禁食要求、既往麻醉反应和相关风险必须由麻醉医生结合病情说明。"
                    "如有药物过敏或既往麻醉异常，请主动告知医护人员。"
                ),
                "importance_level": "critical",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            }
        ],
    },
    "blood_transfusion": {
        "title": "输血知情同意提醒",
        "document_version": "TRANSFUSION-REMINDER-1.0",
        "clauses": [
            {
                "clause_code": "TRANSFUSION_EXPLANATION",
                "clause_name": "输血目的与风险需由医生解释",
                "patient_content": (
                    "输血指征、可能获益、替代方案及发热、过敏等风险需由主管医生说明。"
                    "输血期间如出现发冷、发热、皮疹、胸闷或呼吸困难，请立即告知护士。"
                ),
                "importance_level": "critical",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            }
        ],
    },
    "tobacco": {
        "title": "住院戒烟知情确认",
        "document_version": "TOBACCO-1.0",
        "clauses": [
            {
                "clause_code": "NO_SMOKING",
                "clause_name": "住院期间禁止吸烟",
                "patient_content": (
                    "病区为无烟环境。住院期间请勿在病房、卫生间、楼梯间等区域吸烟；"
                    "如需戒烟支持，请联系护士。"
                ),
                "importance_level": "important",
                "mandatory_delivery": True,
                "explicit_confirmation_required": True,
            }
        ],
    },
}


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

    material = _EDUCATION_MATERIALS[category]
    return {
        "success": True,
        "event_id": f"EDU-EVENT-{uuid4().hex.upper()}",
        "material_id": f"EDU-{category.upper()}-V1-L{level}",
        "category": category,
        "level": level,
        "document_version": "1.0",
        "title": material["title"],
        "original_content": material["original_content"],
        "patient_content": material["patient_content"],
        "spoken_content": material["spoken_content"],
        "content": material["original_content"],
        "audio_url": None,
        "source_name": material["source_name"],
        "priority": material["priority"],
        "requires_acknowledgement": True,
        "auto_play": True,
        "clinical_review_status": "pending_hospital_review",
    }


@tool
async def trigger_consent_form(
    form_type: Literal[
        "admission_nursing",
        "surgery",
        "anesthesia",
        "blood_transfusion",
        "tobacco",
    ],
) -> dict[str, Any]:
    """触发知情同意书签署流程（手术、麻醉、输血等）。

    Args:
        form_type: 知情同意书类型（surgery=手术, anesthesia=麻醉,
            blood_transfusion=输血, tobacco=戒烟）。
    """
    if form_type not in _CONSENT_DOCUMENTS:
        return {"success": False, "message": f"不支持的知情同意书类型: {form_type}"}
    logger.info("[Tool] trigger_consent_form: form_type=%s", form_type)

    document = _CONSENT_DOCUMENTS[form_type]
    clauses = [
        {
            "id": f"{form_type}-{item['clause_code']}",
            **item,
            "delivery_status": "pending",
            "listened": False,
            "confirmed": False,
        }
        for item in document["clauses"]
    ]
    return {
        "success": True,
        "event_id": f"CONSENT-EVENT-{uuid4().hex.upper()}",
        "form_id": f"consent_{form_type}_{uuid4().hex}",
        "form_type": form_type,
        "title": document["title"],
        "document_version": document["document_version"],
        "full_text": "\n".join(
            f"{index}. {item['clause_name']}：{item['patient_content']}"
            for index, item in enumerate(clauses, 1)
        ),
        "clauses": clauses,
        "status": "pending_signature",
        "requires_signature": True,
        "auto_play": True,
        "clinical_review_status": "pending_hospital_review",
    }


@tool
async def request_nurse_assistance(
    requested_action: Literal[
        "measure_temperature",
        "measure_blood_pressure",
        "measure_weight",
        "measure_height",
        "other",
    ],
    reason: str,
    urgency: Literal["routine", "urgent"] = "routine",
) -> dict[str, Any]:
    """呼叫护士到床旁完成必须由医护人员执行的操作。

    Args:
        requested_action: 请求护士执行的操作。
        reason: 需要护士到场的具体原因。
        urgency: routine=常规处理，urgent=尽快处理。
    """
    action_labels = {
        "measure_temperature": "测量体温",
        "measure_blood_pressure": "测量血压",
        "measure_weight": "测量体重",
        "measure_height": "测量身高",
        "other": "其他人工护理操作",
    }
    normalized_reason = reason.strip()
    if not normalized_reason:
        return {"success": False, "message": "呼叫护士原因不能为空"}
    action_label = action_labels[requested_action]
    logger.info(
        "[Tool] request_nurse_assistance: action=%s, urgency=%s, reason=%s",
        requested_action,
        urgency,
        normalized_reason,
    )
    return {
        "success": True,
        "event_id": f"HANDOFF-EVENT-{uuid4().hex.upper()}",
        "request_id": f"NURSE-{uuid4().hex.upper()}",
        "requested_action": requested_action,
        "action_label": action_label,
        "reason": normalized_reason,
        "urgency": urgency,
        "priority": "high" if urgency == "urgent" else "medium",
        "title": f"需要护士协助{action_label}",
        "description": normalized_reason,
        "status": "requested",
    }


@tool
async def play_audio(audio_url: str) -> dict[str, Any]:
    """兼容旧协议的音频播放工具。

    患者端宣教和知情同意播报由领域组件自动完成；该工具仅保留为旧调用的明确失败结果，
    防止历史模型把音频 URL 当作已经播放成功。
    """
    logger.info("[Tool] play_audio: audio_url=%s", audio_url)
    return {
        "success": False,
        "message": "play_audio 已由宣教/知情同意领域组件接管，请勿直接调用",
    }


# ==================== 工具注册表 ====================

# LangChain BaseTool 注册表（名称 → 工具对象），供执行路由与 schema 生成复用
_TOOL_OBJECTS: list[BaseTool] = [
    get_education_material,
    trigger_consent_form,
    request_nurse_assistance,
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
