"""对话交互路由
作用：提供开始对话、发送患者消息（旧路径）与查询对话历史接口，返回裸载荷。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.dialog import (
    DialogHistoryResponse,
    DialogResponse,
    SendMessageRequest,
    SendMessageResponse,
    StartDialogRequest,
)
from app.services import dialog_service

router = APIRouter(prefix="/api/dialog", tags=["dialog"])


@router.post("/start", summary="开始对话")
def start_dialog(
    req: StartDialogRequest, db: Session = Depends(get_db)
) -> DialogResponse:
    """开始对话
    Args:
        - req: 开始对话请求
        - db: 数据库会话
    Return:
        - DialogResponse: 会话详情（裸载荷）
    """
    return dialog_service.start_dialog(db, req)


@router.post(
    "/{session_no}/message",
    summary="发送患者消息（旧路径，保留兼容）",
)
async def send_message_legacy(
    session_no: str, req: SendMessageRequest, db: Session = Depends(get_db)
) -> SendMessageResponse:
    """发送患者消息（旧路径）
    作用：落库消息并发布事件，AI 回复经 SSE 异步回推。保留此路径用于兼容。
    Args:
        - session_no: 会话编号（路径参数，优先级高于 body）
        - req: 发送消息请求
        - db: 数据库会话
    Return:
        - SendMessageResponse: 消息落库结果（裸载荷）
    """
    # 优先使用路径参数中的 session_no
    req.session_id = session_no
    return await dialog_service.send_message(db, req)


@router.get(
    "/{session_no}/history",
    summary="获取对话历史",
)
async def get_history(
    session_no: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500, description="返回消息数量上限"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> DialogHistoryResponse:
    """获取对话历史
    Args:
        - session_no: 会话编号
        - db: 数据库会话
        - limit: 返回消息数量上限（默认100）
        - offset: 偏移量（默认0）
    Return:
        - DialogHistoryResponse: 历史消息列表（裸载荷）
    """
    return await dialog_service.get_history(db, session_no, limit, offset)
