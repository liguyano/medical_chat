"""把量表目标与患者交流场景分开，原始条件只作后台参考。"""

import json

from ..schedule_agent import QuestionTask


def supports_life_scene(task: QuestionTask) -> bool:
    """普通交谈默认用场景，固定施测和必须直接核实的项目优先。"""
    name = getattr(task, "question_name", "")
    text = f"{name} {getattr(task, 'section_name', None) or ''}"
    if (getattr(task, "scale_code", None) or "").lower() in {"mmse", "moca", "mini-cog"}:
        return False
    if name.strip().lower() in {"bp", "t", "p", "r", "spo2", "hr"}:
        return False
    return not any(
        word in text
        for word in (
            "过敏",
            "疼痛",
            "意识",
            "定向",
            "记忆",
            "复述",
            "命名",
            "计算",
            "认知",
            "注意力",
            "指令",
            "画钟",
            "回忆",
            "阅读",
            "书写",
            "血压",
            "体温",
            "脉搏",
            "血氧",
            "呼吸",
            "胸痛",
        )
    )


def question_conversation_context(task: QuestionTask) -> dict[str, str]:
    """所有普通目标都带生活场景要求，进餐额外提供动作路径；不改变题目或计分。"""
    reference = task.patient_text or task.question_name
    name = f"{getattr(task, 'question_name', '')} {task.question_code}".lower()
    context = {"clinical_reference": reference}
    if not supports_life_scene(task):
        return context
    context["scene_guidance"] = (
        "此事实必须融入相关生活场景话题，通过具体经历和动作了解；"
        "不能聊完兴趣再切回量表问法，不只给能力判断加过渡；原题只作后台条件，缺少明确证据不填答案。"
    )
    if any(word in name for word in ("进食", "吃饭", "feeding", "eating")):
        context["scene_guidance"] = (
            "进餐场景：转入本话题时先聊喜欢的食物或最近一顿饭，等回答后，顺着患者说的食物聊餐具和实际进餐动作。"
            "例如喜欢面条→吃面条用筷子还是勺子→夹面送入口中时顺手吗；每次只选一个问题，等回答再继续。"
            "已有食物场景就延续，不机械重问喜好。禁止从游戏或其他话题直接跳到“吃饭需要帮忙吗”“能自己吃饭吗”。"
            "旧问句后患者只答好或嗯且没有具体食物场景时，先聊最近一顿吃什么；"
            "禁止用“自己能吃还是需要人帮”重问能力来澄清。"
            "需要澄清协助时只问这顿具体食物的进餐过程，不让患者评价整体能力。"
            "喜好或餐具不能证明自理；做饭也不能证明独立进食。只有完整明确的进餐动作与协助原话才能填相应答案，"
            "缺项保持缺失，依据原题时间范围和选项条件继续具体澄清，不反复兜圈。"
            "clinical_reference是后台事实范围和条件，不是患者问句，禁止照读。"
        )
    return context


def dialogue_reference(task: QuestionTask) -> str:
    """所有普通题区分后台事实与生活场景，固定施测保留原句。"""
    context = question_conversation_context(task)
    return (
        json.dumps(context, ensure_ascii=False)
        if "scene_guidance" in context
        else context["clinical_reference"]
    )
