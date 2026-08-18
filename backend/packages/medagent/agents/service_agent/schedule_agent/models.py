"""Schedule Agent 数据模型
作用：定义与业务应用层无关的量表任务、工具调用和调度输出结构。
"""

from typing import Any

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    """量表问题选项。"""

    option_code: str
    option_label: str
    option_value: str
    clinical_score: float | None = None
    requires_follow_up: bool = False


class QuestionTask(BaseModel):
    """单个量表问题任务。"""

    question_id: int
    question_code: str
    question_name: str
    patient_text: str
    question_type: str
    required: bool
    sort_no: int
    section_name: str | None = None
    scale_code: str | None = None
    options: list[QuestionOption] = Field(default_factory=list)
    completed: bool = False
    dialogue_goal: str = ""
    source_question_ids: list[int] = Field(default_factory=list)


class SchedulePlanDraft(BaseModel):
    """Schedule Agent 生成的问诊计划草稿。"""

    ordered_question_codes: list[str] = Field(default_factory=list)
    opening_guidance: str = ""
    planning_reason: str = ""


class ScheduleTaskTodo(BaseModel):
    """可恢复的会话级量表问诊计划。"""

    session_id: str
    tasks: list[QuestionTask] = Field(default_factory=list)
    opening_guidance: str = ""
    planning_reason: str = ""
    plan_version: str = "1.0"


class ToolCallRecord(BaseModel):
    """一条已经执行的工具调用记录。"""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScheduleAnalysis(BaseModel):
    """大模型对对话进度的结构化分析。"""

    is_deviation: bool = False
    reason: str = ""
    completed_questions: list[str] = Field(default_factory=list)
    current_focus: str = ""
    suggested_action: str = ""


class ScheduleAgentOutput(BaseModel):
    """Schedule Agent 的结构化输出。"""

    checked: bool = Field(default=True, description="本轮是否实际执行了调度检查")
    is_deviation: bool = Field(description="是否需要约束下一轮对话")
    constraint_prompt: str = Field(default="", description="下一轮对话约束提示")
    completed_questions: list[str] = Field(default_factory=list)
    remaining_questions: list[str] = Field(default_factory=list)
    missing_tool_calls: list[str] = Field(default_factory=list)
    next_suggested_question: str = Field(default="", description="建议下一个问题文本")
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
