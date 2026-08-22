"""患者门户补充域 API Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PatientTaskVerifyRequest(BaseModel):
    """按任务编号和证件后四位核验当前在院患者。"""

    model_config = ConfigDict(extra="forbid")

    task_no: str = Field(..., min_length=1, max_length=64)
    id_card_suffix: str = Field(
        ...,
        min_length=4,
        max_length=4,
        pattern=r"^[0-9Xx]{4}$",
    )


class PatientScanTokenCreateRequest(BaseModel):
    """医护端创建一次性扫码令牌。"""

    model_config = ConfigDict(extra="forbid")

    task_no: str = Field(..., min_length=1, max_length=64)
    expires_in_seconds: int = Field(default=300, ge=30, le=900)


class PatientScanVerifyRequest(BaseModel):
    """患者端核验一次性扫码令牌。"""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=24, max_length=256)


class PatientNotificationDto(BaseModel):
    """患者通知返回结构。"""

    id: int
    notification_no: str
    notification_type: str
    title: str
    content: str
    priority: str
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class WardGuideDto(BaseModel):
    """病区指南条目。"""

    id: int
    guide_code: str
    category: str
    title: str
    content: str
    department_name: str | None = None
    ward_name: str | None = None
    sort_no: int


class PatientAssistantSessionCreateRequest(BaseModel):
    """创建住院助手会话。"""

    model_config = ConfigDict(extra="forbid")

    channel_type: Literal["text", "voice"] = "text"


class PatientAssistantMessageRequest(BaseModel):
    """发送独立住院生活问题。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=2000)
    client_message_id: str | None = Field(default=None, max_length=128)


class PatientAssistantMessageDto(BaseModel):
    """助手消息。"""

    message_no: str
    role: Literal["patient", "assistant", "system"]
    content: str
    result_status: str | None = None
    source_guide_id: int | None = None
    occurred_at: datetime


class PatientAssistantSessionDto(BaseModel):
    """助手会话及历史。"""

    session_no: str
    channel_type: str
    session_status: str
    handoff_required: bool
    handoff_reason: str | None = None
    messages: list[PatientAssistantMessageDto] = Field(default_factory=list)


class ConsentPlaybackRequest(BaseModel):
    """记录条款音频播放操作。"""

    model_config = ConfigDict(extra="forbid")

    clause_id: int
    event_type: Literal["start", "pause", "resume", "complete", "replay"]
    position_seconds: int = Field(default=0, ge=0, le=86400)
    client_invocation_id: str | None = Field(default=None, max_length=128)


class ConsentClauseConfirmRequest(BaseModel):
    """确认单条知情同意条款。"""

    model_config = ConfigDict(extra="forbid")

    confirmation_result: Literal["已理解并确认", "未理解", "拒绝", "不确定"]
    patient_reply: str | None = Field(default=None, max_length=2000)


class ConsentParticipantRequest(BaseModel):
    """签署参与人信息。"""

    model_config = ConfigDict(extra="forbid")

    participant_type: Literal["患者", "家属"] = "患者"
    participant_name: str = Field(..., min_length=1, max_length=128)
    relationship_to_patient: str | None = Field(default=None, max_length=64)


class ConsentSnapshotDto(BaseModel):
    """任务绑定的知情同意文档快照。"""

    task_no: str
    record_id: int
    consent_code: str
    consent_name: str
    consent_type: str
    document_version: str
    full_text: str
    record_status: str
    patient_confirmed: bool
    participant_type: str
    clauses: list[dict[str, Any]] = Field(default_factory=list)
    confirmations: list[dict[str, Any]] = Field(default_factory=list)
    playback: list[dict[str, Any]] = Field(default_factory=list)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    signatures: list[dict[str, Any]] = Field(default_factory=list)
