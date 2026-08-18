"""Schedule Agent 模块
作用：调度智能体，监控对话进度，检测偏离。
"""

from .agent import ScheduleAgent
from .models import (
    QuestionOption,
    QuestionTask,
    ScheduleAgentOutput,
    SchedulePlanDraft,
    ScheduleTaskTodo,
    ToolCallRecord,
)
from .prompts import (
    DEVIATION_CHECK_SYSTEM_PROMPT,
    TASK_TODO_SYSTEM_PROMPT,
    build_deviation_check_prompt,
    build_task_todo_prompt,
    get_few_shot_examples_text,
)

__all__ = [
    "DEVIATION_CHECK_SYSTEM_PROMPT",
    "TASK_TODO_SYSTEM_PROMPT",
    "QuestionOption",
    "QuestionTask",
    "ScheduleAgent",
    "ScheduleAgentOutput",
    "SchedulePlanDraft",
    "ScheduleTaskTodo",
    "ToolCallRecord",
    "build_deviation_check_prompt",
    "build_task_todo_prompt",
    "get_few_shot_examples_text",
]
