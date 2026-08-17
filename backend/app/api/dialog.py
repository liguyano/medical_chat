"""对话交互路由
作用：提供患者答案提交与对话历史查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.dialog import (
    DialogHistoryResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from app.schemas.response import ApiResponse, ok
from app.services import dialog_service

router = APIRouter(prefix="/api/dialog", tags=["dialog"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/message",
    response_model=ApiResponse[SendMessageResponse],
    summary="发送患者答案",
)
async def send_message(
    req: SendMessageRequest,
    db: DbSession,
) -> dict:
    """保存患者答案，AI下一问通过SSE回推。"""
    return ok(await dialog_service.send_message(db, req))


@router.get(
    "/{session_no}/history",
    response_model=ApiResponse[DialogHistoryResponse],
    summary="获取对话历史",
)
async def get_history(
    session_no: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """分页查询患者答案与AI问句。"""
    return ok(await dialog_service.get_history(db, session_no, limit, offset))
