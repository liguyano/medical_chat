"""对话交互相关 Schema
作用：定义患者发送答案和对话历史查询的请求响应结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    """发送患者答案请求。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="会话编号")
    task_id: int | str = Field(..., description="任务主键或任务编号")
    content: str = Field(..., min_length=1, description="患者答案文本")
    client_message_id: str = Field(..., min_length=1, description="客户端幂等消息ID")
    input_mode: Literal["text"] = Field(default="text", description="第一期仅支持文本")


class SendMessageResponse(BaseModel):
    """发送消息响应
    作用：确认患者答案已落库并发布，AI下一问由SSE异步回推。
    """

    session_no: str
    message_no: str
    turn_no: int
    intercepted: bool = False


class MessageItem(BaseModel):
    """对话历史消息项。"""

    message_no: str
    turn_no: int
    role_type: str
    message_type: str
    content_text: str | None = None
    audio_url: str | None = None
    asr_text: str | None = None
    tts_text: str | None = None
    occurred_at: datetime | None = None


class DialogHistoryResponse(BaseModel):
    """对话历史响应。"""

    session_id: str
    task_id: int
    task_no: str
    session_status: str
    current_cicare_stage: str | None = None
    answered_question_count: int = 0
    total_question_count: int = 0
    ai_summary: str | None = None
    total: int
    messages: list[MessageItem] = Field(default_factory=list)
