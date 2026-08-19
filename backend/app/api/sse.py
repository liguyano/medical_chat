"""SSE 流式推送路由
作用：提供患者端与医护端的对话事件订阅接口，消费 dialog_stream 并以 SSE 推送。
      支持 Last-Event-ID 断线续读与 30 秒心跳保活。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import require_patient, require_staff
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.base import get_db
from app.models.interaction import InteractionSession
from app.models.patient_task import Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.services.sse_service import (
    HEARTBEAT_INTERVAL,
    stream_dialog_events,
    stream_nurse_events,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sse", tags=["sse"])


def _ensure_session_exists(db: Session, session_no: str) -> None:
    """校验会话存在
    Args:
        - db: 数据库会话
        - session_no: 会话编号
    """
    exists = db.scalar(
        select(InteractionSession.id).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if exists is None:
        raise AppError(ErrorCode.ERR_SSE_001)


def _ensure_session_patient(
    db: Session,
    session_no: str,
    patient_id: int,
) -> None:
    """校验患者只能订阅本人会话。"""
    session_patient_id = db.scalar(
        select(InteractionSession.patient_id).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session_patient_id != patient_id:
        raise AppError(ErrorCode.ERR_SSE_001)


@router.get("/dialog/{session_no}", summary="患者端订阅对话事件流")
async def subscribe_dialog(
    session_no: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    patient_context: Annotated[
        tuple[Patient, PatientEncounter],
        Depends(require_patient),
    ],
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    last_event_id: str | None = Query(default=None),
) -> EventSourceResponse:
    """患者端订阅对话事件流
    作用：消费 dialog_stream:{session_no}，实时推送 AI 回复与进度事件。
    Args:
        - session_no: 会话编号
        - request: 请求对象（用于检测客户端断开）
        - db: 数据库会话
        - last_event_id: 断线重连起点消息 ID（HTTP 头 Last-Event-ID）
    Return:
        - EventSourceResponse: SSE 事件流
    """
    _ensure_session_exists(db, session_no)
    patient, _ = patient_context
    _ensure_session_patient(db, session_no, patient.id)
    resume_from = last_event_id_header or last_event_id
    logger.info(f"患者端订阅 SSE: session_no={session_no} last_event_id={resume_from}")
    return EventSourceResponse(
        stream_dialog_events(session_no, resume_from),
        ping=HEARTBEAT_INTERVAL,
    )


@router.get("/monitor/{session_no}", summary="医护端只读监听对话事件流")
async def monitor_dialog(
    session_no: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[StaffAccount, Depends(require_staff)],
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    last_event_id: str | None = Query(default=None),
) -> EventSourceResponse:
    """医护端只读监听对话事件流
    作用：复用 dialog_stream 做单会话只读监听（多会话聚合后补）。
    Args:
        - session_no: 会话编号
        - request: 请求对象
        - db: 数据库会话
        - last_event_id: 断线重连起点消息 ID
    Return:
        - EventSourceResponse: SSE 事件流
    """
    _ensure_session_exists(db, session_no)
    resume_from = last_event_id_header or last_event_id
    logger.info(f"医护端监听 SSE: session_no={session_no} last_event_id={resume_from}")
    return EventSourceResponse(
        stream_dialog_events(session_no, resume_from),
        ping=HEARTBEAT_INTERVAL,
    )


@router.get("/nurse/alerts", summary="责任护士订阅全局人工介入提醒")
async def subscribe_nurse_alerts(
    request: Request,
    staff: Annotated[StaffAccount, Depends(require_staff)],
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    last_event_id: str | None = Query(default=None),
) -> EventSourceResponse:
    """订阅 nurse_stream:{staff_id}，在医护端任意页面接收患者呼叫。"""
    resume_from = last_event_id_header or last_event_id
    logger.info(
        "医护端订阅全局提醒 SSE: staff_id=%s last_event_id=%s",
        staff.id,
        resume_from,
    )
    return EventSourceResponse(
        stream_nurse_events(staff.id, resume_from),
        ping=HEARTBEAT_INTERVAL,
    )
