"""事件Schema定义
作用：定义Redis Stream通信层的事件结构
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """事件类型枚举"""

    DIALOG_TURN = "dialog_turn"  # 对话轮次事件
    DIALOG_TEXT = "dialog_text"  # 文本输出事件
    DIALOG_AUDIO = "dialog_audio"  # 音频输出事件
    DIALOG_MESSAGE = "dialog_message"  # AI问诊问题事件（Dialog Agent输出）
    ASSISTANT_MESSAGE_STARTED = "assistant_message_started"  # AI消息开始生成
    PATIENT_ANSWER = "patient_answer"  # 患者答案事件（POST /api/dialog/message输入）
    TOOL_CALL = "tool_call"  # 工具调用事件
    CONSTRAINT = "constraint"  # 约束提示事件
    SESSION_START = "session_start"  # 会话启动事件
    SESSION_END = "session_end"  # 会话结束事件
    EXTRACTION_RESULT = "extraction_result"  # 字段抽取结果事件
    AGENT_ERROR = "agent_error"  # Agent 真实模型调用失败事件


class BaseEvent(BaseModel):
    """基础事件Schema
    作用：所有事件的基类
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    session_id: str
    task_id: int | str | None = None
    message_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = Field(default="1.0")


class DialogTurnEvent(BaseEvent):
    """对话轮次事件
    作用：每轮对话完成后发布
    """

    event_type: EventType = EventType.DIALOG_TURN
    turn_number: int
    question: str  # 患者问题
    answer: str  # AI回答
    tool_calls: list[dict[str, Any]] | None = None  # 工具调用记录
    metadata: dict[str, Any] | None = None


class DialogTextEvent(BaseEvent):
    """文本输出事件
    作用：流式文本输出时发布
    """

    event_type: EventType = EventType.DIALOG_TEXT
    turn_number: int
    text_chunk: str  # 文本片段
    generation_id: str = ""
    question_id: str | None = None
    is_final: bool = False  # 是否最后一片


class DialogAudioEvent(BaseEvent):
    """音频输出事件
    作用：流式音频输出时发布
    """

    event_type: EventType = EventType.DIALOG_AUDIO
    turn_number: int
    audio_url: str  # 音频URL（OSS/本地）
    audio_format: str = "pcm"  # pcm | opus | mp3
    duration_ms: int | None = None


class ToolCallEvent(BaseEvent):
    """工具调用事件
    作用：AI调用工具时发布
    """

    event_type: EventType = EventType.TOOL_CALL
    turn_number: int
    tool_name: str  # 工具名称
    tool_args: dict[str, Any]  # 工具参数
    tool_result: Any | None = None  # 工具返回值


class ConstraintEvent(BaseEvent):
    """约束提示事件
    作用：Schedule Agent检测到偏离时发布
    """

    event_type: EventType = EventType.CONSTRAINT
    constraint_type: str  # deviation | missing_tool | timeout
    constraint_prompt: str  # 约束提示词
    remaining_tasks: list[str]  # 剩余任务列表


class SessionStartEvent(BaseEvent):
    """会话启动事件
    作用：对话会话创建时发布
    """

    event_type: EventType = EventType.SESSION_START
    patient_id: str
    task_id: str
    form_ids: list[str]  # 量表ID列表


class SessionEndEvent(BaseEvent):
    """会话结束事件
    作用：对话会话结束时发布
    """

    event_type: EventType = EventType.SESSION_END
    end_reason: str  # completed | timeout | nurse_intervention
    total_turns: int
    duration_seconds: int


class ExtractionResultEvent(BaseEvent):
    """字段抽取结果事件
    作用：Field Extraction Agent抽取完成后发布
    """

    event_type: EventType = EventType.EXTRACTION_RESULT
    form_id: str | None = None
    extracted_fields: dict[str, Any]  # {question_id: value}
    confidence_scores: dict[str, float]  # {question_id: confidence}


class DialogMessageEvent(BaseEvent):
    """AI问诊问题事件
    作用：Dialog Agent产出下一个问诊问题时发布（供患者端SSE消费）
    """

    event_type: EventType = EventType.DIALOG_MESSAGE
    turn_number: int
    role: str = "assistant"  # assistant（AI问）
    content: str  # 问诊问题文本
    question_id: str | None = None  # 对应Task-todo问题ID
    is_opening: bool = False  # 是否首个问诊问题
    generation_id: str | None = None


class AssistantMessageStartedEvent(BaseEvent):
    """AI 消息开始事件
    作用：模型开始生成前建立前端占位消息，并关联 Redis 完整文本快照。
    """

    event_type: EventType = EventType.ASSISTANT_MESSAGE_STARTED
    turn_number: int
    generation_id: str
    question_id: str | None = None
    role: str = "assistant"


class PatientAnswerEvent(BaseEvent):
    """患者答案事件
    作用：POST /api/dialog/message接收患者输入后发布（供三个Agent消费）
    """

    event_type: EventType = EventType.PATIENT_ANSWER
    turn_number: int
    role: str = "user"  # user（患者答）
    content: str  # 患者答案文本
    client_message_id: str | None = None  # 前端消息ID
    input_mode: str = "text"  # text | voice


class AgentErrorEvent(BaseEvent):
    """Agent 错误事件
    作用：向前端明确报告真实模型调用失败，禁止使用静态问题伪装成功。
    """

    event_type: EventType = EventType.AGENT_ERROR
    agent_name: str
    error_code: str
    message: str
    retrying: bool = True
    generation_id: str | None = None


# 事件类型映射
EVENT_TYPE_MAP = {
    EventType.DIALOG_TURN: DialogTurnEvent,
    EventType.DIALOG_TEXT: DialogTextEvent,
    EventType.DIALOG_AUDIO: DialogAudioEvent,
    EventType.DIALOG_MESSAGE: DialogMessageEvent,
    EventType.ASSISTANT_MESSAGE_STARTED: AssistantMessageStartedEvent,
    EventType.PATIENT_ANSWER: PatientAnswerEvent,
    EventType.AGENT_ERROR: AgentErrorEvent,
    EventType.TOOL_CALL: ToolCallEvent,
    EventType.CONSTRAINT: ConstraintEvent,
    EventType.SESSION_START: SessionStartEvent,
    EventType.SESSION_END: SessionEndEvent,
    EventType.EXTRACTION_RESULT: ExtractionResultEvent,
}
