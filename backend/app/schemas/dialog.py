"""对话交互相关 Schema
作用：定义开始对话、发送消息的请求与响应结构。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StartDialogRequest(BaseModel):
    """开始对话请求
    作用：基于已创建的评估任务开启一次交互会话。
    """

    task_no: str = Field(..., description="关联的评估任务编号")
    scale_codes: list[str] = Field(
        default_factory=list, description="本次对话涉及的量表编码列表"
    )
    channel_type: str = Field(default="text", description="渠道类型：text | voice")
    engine_type: str = Field(
        default="text", description="对话引擎类型：doubao | text"
    )


class DialogResponse(BaseModel):
    """会话创建响应
    作用：返回新建交互会话的编号与状态。
    """

    session_no: str = Field(..., description="会话编号")
    task_no: str = Field(..., description="关联任务编号")
    session_status: str = Field(..., description="会话状态")
    started_at: datetime | None = Field(default=None, description="会话开始时间")


class SendMessageRequest(BaseModel):
    """发送患者消息请求
    作用：承载患者一轮输入，支持文本与 Base64 音频。
    """

    session_id: str = Field(..., description="会话编号")
    task_id: str = Field(..., description="任务编号")
    content: str = Field(..., description="患者文本内容")
    client_message_id: str = Field(..., description="客户端消息唯一标识")
    input_mode: str = Field(default="text", description="输入模式：text | voice")
    audio_base64: str | None = Field(default=None, description="Base64 编码的音频（语音模式）")
    audio_format: str = Field(default="pcm", description="音频格式：pcm | opus | mp3")
    message_type: str = Field(default="text", description="消息类型：text | audio")


class SendMessageResponse(BaseModel):
    """发送消息响应
    作用：返回落库消息编号与轮次；AI 回复经 SSE 异步回推，不在此同步返回。
    """

    session_no: str = Field(..., description="会话编号")
    message_no: str = Field(..., description="消息编号")
    turn_no: int = Field(..., description="轮次序号")
    intercepted: bool = Field(default=False, description="是否命中关键词约束")


class MessageItem(BaseModel):
    """对话历史消息项"""

    message_no: str = Field(..., description="消息编号")
    turn_no: int = Field(..., description="轮次序号")
    role_type: str = Field(..., description="角色：患者 | AI | 护士 等")
    message_type: str = Field(..., description="消息类型")
    content_text: str | None = Field(default=None, description="文本内容")
    occurred_at: datetime | None = Field(default=None, description="发生时间")


class DialogHistoryResponse(BaseModel):
    """对话历史响应（对齐前端 DialogHistoryResponse 契约）"""

    session_id: str = Field(..., description="会话编号")
    task_id: str = Field(..., description="任务编号")
    session_status: str | None = Field(default=None, description="会话状态")
    current_cicare_stage: str | None = Field(default=None, description="当前CICARE阶段")
    answered_question_count: int | None = Field(default=None, description="已回答题目数")
    total_question_count: int | None = Field(default=None, description="总题目数")
    ai_summary: str | None = Field(default=None, description="AI总结")
    total: int = Field(..., description="消息总数")
    messages: list[MessageItem] = Field(default_factory=list, description="消息列表")
