"""把量表目标与患者交流场景分开，原始条件只作后台参考。"""

import json

from ..schedule_agent import QuestionTask


def question_conversation_context(task: QuestionTask) -> dict[str, str]:
    """为进餐目标提供具体动作路径，其余目标保持原有参考；不改变题目或计分。"""
    reference = task.patient_text or task.question_name
    name = f"{getattr(task, 'question_name', '')} {task.question_code}".lower()
    context = {"clinical_reference": reference}
    fixed_scale = (getattr(task, "scale_code", None) or "").lower() in {"mmse", "moca", "mini-cog"}
    if not fixed_scale and any(word in name for word in ("进食", "吃饭", "feeding", "eating")):
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
    """普通题保持原问法参考，进餐题显式区分后台条件和场景路径。"""
    context = question_conversation_context(task)
    return (
        json.dumps(context, ensure_ascii=False)
        if "scene_guidance" in context
        else context["clinical_reference"]
    )
