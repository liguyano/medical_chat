"""对话交互统一路由
作用：提供统一消息发送接口（POST /api/dialog/message），返回裸载荷。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.dialog import SendMessageRequest, SendMessageResponse
from app.services import dialog_service

router = APIRouter(prefix="/api/dialog", tags=["dialog"])


@router.post("/message", summary="发送患者消息（统一入口）")
async def send_message(
    req: SendMessageRequest, db: Session = Depends(get_db)
) -> SendMessageResponse:
    """发送患者消息（统一入口）
    作用：落库消息并发布事件，AI 回复经 SSE 异步回推。
    Args:
        - req: 发送消息请求（包含 session_id/task_id/content/client_message_id/input_mode）
        - db: 数据库会话
    Return:
        - SendMessageResponse: 消息落库结果（裸载荷）
    """
    return await dialog_service.send_message(db, req)
