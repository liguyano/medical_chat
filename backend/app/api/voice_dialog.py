"""实时语音对话 API。

作用：提供患者端 WebSocket 音频交互和患者/医护端受保护音频回放接口。
业务事件仍由 Voice Gateway 写入 Redis Stream，页面通过 SSE 消费。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_staff_or_patient
from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models import base as model_base
from app.models.base import get_db
from app.models.interaction import InteractionSession
from app.models.patient_task import Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.services.agent_dispatch_service import build_session_agent_payload
from app.services.dialog_audio_store import DialogAudioStore
from app.services.voice_gateway import voice_gateway
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice-dialog"])
DbSession = Annotated[Session, Depends(get_db)]


def _load_session(session_no: str) -> tuple[int, int, int, dict, list[str]]:
    """加载会话主键、任务主键、患者主键和语音网关所需配置。"""
    if model_base.SessionLocal is None:
        raise RuntimeError("数据库未初始化")
    with model_base.SessionLocal() as db:
        session = db.scalar(
            select(InteractionSession).where(
                InteractionSession.session_no == session_no,
                InteractionSession.deleted == 0,
            )
        )
        if session is None:
            raise AppError(ErrorCode.ERR_DIALOG_001)
        if session.session_status not in {"pending", "active"}:
            raise AppError(ErrorCode.ERR_DIALOG_002)
        patient_info, task_config = build_session_agent_payload(db, session)
        return (
            session.task_id,
            session.patient_id,
            session.encounter_id,
            patient_info,
            list(task_config.get("scale_codes") or []),
        )


def _authenticate_patient_websocket(websocket: WebSocket) -> tuple[int, int]:
    """使用患者 HttpOnly Cookie 校验 WebSocket。"""
    cookie_name = get_app_config().security.patient_session_cookie
    token = websocket.cookies.get(cookie_name)
    if not token:
        raise AppError(ErrorCode.ERR_PATIENT_003)
    payload = get_redis().get(f"patient_auth:{token}")
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.ERR_PATIENT_003)
    return int(payload.get("patient_id")), int(payload.get("encounter_id"))


@router.websocket("/api/ws/dialog/{session_no}/voice")
async def dialog_voice_socket(websocket: WebSocket, session_no: str) -> None:
    """患者端实时语音 WebSocket。"""
    await websocket.accept()
    session = None
    try:
        patient_id, _ = _authenticate_patient_websocket(websocket)
        task_id, session_patient_id, _encounter_id, patient_info, scale_codes = _load_session(
            session_no
        )
        if patient_id != session_patient_id:
            raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权访问该语音会话")
        session = await voice_gateway.get_or_create(
            session_no=session_no,
            task_id=task_id,
            patient_id=patient_id,
            patient_info=patient_info,
            scale_codes=scale_codes,
        )
        await voice_gateway.attach(session, websocket)

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await voice_gateway.append_audio(session, bytes(message["bytes"]))
                continue
            raw_text = message.get("text")
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "code": "INVALID_MESSAGE", "message": "控制消息格式错误"}
                )
                continue
            message_type = str(payload.get("type") or "")
            if message_type == "start":
                await websocket.send_json({"type": "state", "state": "listening"})
            elif message_type == "commit":
                await voice_gateway.commit(session)
            elif message_type == "interrupt":
                await voice_gateway.interrupt(session)
            elif message_type == "pause":
                await websocket.send_json({"type": "state", "state": "paused"})
            elif message_type == "resume":
                await websocket.send_json({"type": "state", "state": "listening"})
            elif message_type == "close":
                break
            else:
                await websocket.send_json(
                    {"type": "error", "code": "INVALID_MESSAGE", "message": "不支持的控制消息"}
                )
    except WebSocketDisconnect:
        pass
    except AppError as exc:
        logger.warning("语音 WebSocket 业务拒绝: session=%s code=%s", session_no, exc.code)
        try:
            await websocket.send_json(
                {"type": "error", "code": exc.code.value, "message": exc.message}
            )
        except RuntimeError:
            logger.debug("语音 WebSocket 已无法发送拒绝消息: session=%s", session_no)
        await websocket.close(code=4403)
    except Exception:
        logger.exception("语音 WebSocket 处理失败: session=%s", session_no)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "VOICE_GATEWAY_ERROR",
                    "message": "语音服务暂时不可用，请切换文字输入",
                }
            )
        except RuntimeError:
            logger.debug("语音 WebSocket 已无法发送错误消息: session=%s", session_no)
        await websocket.close(code=1011)
    finally:
        if session is not None:
            await voice_gateway.detach(session, websocket)


@router.get("/api/dialog/{session_no}/audio/{generation_id}/{filename}")
async def get_dialog_audio(
    session_no: str,
    generation_id: str,
    filename: str,
    db: DbSession,
    actor: Annotated[
        StaffAccount | tuple[Patient, PatientEncounter],
        Depends(require_staff_or_patient),
    ],
):
    """读取受保护的语音文件。"""
    session = db.scalar(
        select(InteractionSession).where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
        )
    )
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    if isinstance(actor, tuple) and session.patient_id != actor[0].id:
        raise AppError(ErrorCode.ERR_DIALOG_004, "当前患者无权访问该音频")
    try:
        path = DialogAudioStore().resolve(
            session_no=session_no,
            generation_id=generation_id,
            filename=filename,
        )
    except ValueError as exc:
        raise AppError(ErrorCode.ERR_COMMON_001, "音频路径无效") from exc
    if not path.is_file():
        raise AppError(ErrorCode.ERR_COMMON_001, "音频文件不存在", http_status=404)
    media_type = "application/json" if filename.endswith(".json") else "audio/wav"
    return FileResponse(path, media_type=media_type, filename=path.name)
