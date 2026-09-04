"""对话单轮选题协议，应用层负责候选校验与持久化。"""

from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool


@tool
async def report_question_choice(
    selected_question_id: int | None,
    active_question_id: int | None,
) -> dict:
    """在本轮完成前报告实际选题，用于记录题目关联，不作为患者输出前置门禁。

    Args:
        selected_question_id: 本轮新问的候选题 ID；不问新题时必须为 null。
        active_question_id: 新题时等于 selected_question_id；继续澄清上一题时保留原当前题 ID；普通聊天为 null。
    """
    return {"success": False, "message": "选题必须由会话应用层校验"}


QUESTION_CHOICE_TOOL = convert_to_openai_tool(report_question_choice)
