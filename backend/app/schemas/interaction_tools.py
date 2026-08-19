"""对话工具交互 Schema
作用：定义患者主动呼叫、知情同意签署与工具状态更新接口的请求结构。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HandoffRequest(BaseModel):
    """患者或前端主动呼叫医护请求。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str | int | None = None
    reason: str = Field(..., min_length=1, max_length=1000)
    requested_action: Literal[
        "measure_temperature",
        "measure_blood_pressure",
        "measure_weight",
        "measure_height",
        "other",
    ] = "other"
    urgency: Literal["routine", "urgent"] = "routine"


class HandoffResolveRequest(BaseModel):
    """医护处理人工介入请求。"""

    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=128)
    resolution: str | None = Field(default=None, max_length=1000)


class ConsentSignRequest(BaseModel):
    """患者知情同意签署请求。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str | int
    form_id: str
    document_version: str | None = None
    participant_name: str = Field(..., min_length=1, max_length=128)
    decision: Literal["agreed", "refused", "needs_explanation"]
    signature_data: str | None = None
    clauses: list[dict[str, Any]] = Field(default_factory=list)
