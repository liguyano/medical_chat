"""对话交互路由
作用：提供开始对话、发送患者消息与查询对话历史接口，返回统一响应结构。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.dialog import (
    DialogHistoryResponse,
    DialogResponse,
    SendMessageRequest,
    SendMessageResponse,
    StartDialogRequest,
)
from app.schemas.response import ApiResponse, ok
from app.services import dialog_service

router = APIRouter(prefix="/api/dialog", tags=["dialog"])


@router.post("/start", response_model=ApiResponse[DialogResponse], summary="开始对话")
def start_dialog(req: StartDialogRequest, db: Session = Depends(get_db)) -> dict:
    """开始对话
    Args:
        - req: 开始对话请求
        - db: 数据库会话
    Return:
        - 统一响应，data 为会话详情
    """
    data = dialog_service.start_dialog(db, req)
    return ok(data)


@router.post(
    "/{session_no}/message",
    response_model=ApiResponse[SendMessageResponse],
    summary="发送患者消息",
)
async def send_message(
    session_no: str, req: SendMessageRequest, db: Session = Depends(get_db)
) -> dict:
    """发送患者消息
    作用：落库消息并发布事件，AI 回复经 SSE 异步回推。
    Args:
        - session_no: 会话编号
        - req: 发送消息请求
        - db: 数据库会话
    Return:
        - 统一响应，data 为消息落库结果
    """
    data = await dialog_service.send_message(db, session_no, req)
    return ok(data)


@router.get(
    "/{session_no}/history",
    response_model=ApiResponse[DialogHistoryResponse],
    summary="获取对话历史",
)
async def get_history(session_no: str, db: Session = Depends(get_db)) -> dict:
    """获取对话历史
    Args:
        - session_no: 会话编号
        - db: 数据库会话
    Return:
        - 统一响应，data 为历史消息列表
    """
    data = await dialog_service.get_history(db, session_no)
    return ok(data)
