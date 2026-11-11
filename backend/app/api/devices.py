"""嵌入式设备 HTTP 轮次接口。"""

import asyncio
import audioop
import base64
import hashlib
import hmac
import io
import logging
import re
import time
import wave
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import require_staff
from app.api.voice_dialog import _load_session
from app.models.base import get_db
from app.models.staff_account import StaffAccount
from app.schemas.response import ok
from app.services.device_registry import (
    approve_registration,
    approved_digest,
    credential_digest,
    current_task,
    heartbeat_key,
    pending_registrations,
    request_registration,
)
from app.services.voice_gateway import voice_gateway
from app.utils.redis_client import get_redis

router = APIRouter(prefix="/api/device", tags=["devices"])
logger = logging.getLogger(__name__)
MAX_PCM_BYTES = 60 * 16000 * 2
ROUND_TTL = 600
MAX_ROUNDS = 64


@dataclass
class DeviceRound:
    digest: str
    expires: float
    status: str = "processing"
    wav: bytes | None = None


rounds: dict[tuple[str, str, str], DeviceRound] = {}
workers: set[asyncio.Task] = set()
DbSession = Annotated[Session, Depends(get_db)]
Staff = Annotated[StaffAccount, Depends(require_staff)]
DeviceId = Annotated[str, Header(alias="X-Device-ID", max_length=64)]
DeviceSecret = Annotated[str, Header(alias="X-Device-Secret")]


class ApprovalRequest(BaseModel):
    verification_code: str = Field(pattern=r"^[0-9A-Fa-f]{8}$")


@router.post("/registration")
def register(device_id: DeviceId, secret: DeviceSecret, db: DbSession):
    return request_registration(db, device_id, secret)


@router.get("/registrations")
def pending(db: DbSession, _: Staff):
    return ok(pending_registrations(db))


@router.post("/registrations/{device_id}/approve")
def approve(device_id: str, body: ApprovalRequest, db: DbSession, staff: Staff):
    approve_registration(db, device_id, body.verification_code.upper(), staff_id=staff.id)
    return ok({"status": "approved"})


def authenticate_device(
    device_id: DeviceId,
    secret: DeviceSecret,
    db: DbSession,
) -> str:
    expected = approved_digest(db, device_id)
    if expected is None or not 1 <= len(secret) <= 256 or not hmac.compare_digest(
        credential_digest(secret), expected
    ):
        raise HTTPException(401, "设备凭据无效")
    return device_id


Device = Annotated[str, Depends(authenticate_device)]


@router.post("/heartbeat")
def heartbeat(device_id: Device):
    get_redis().set(heartbeat_key(device_id), "1", ex=45)
    return {"online": True}


@router.get("/task")
def get_task(device_id: Device):
    task = current_task(device_id)
    return {"task_no": task[0] if task else None, "ready": bool(task and task[2] == "ready")}


def encode_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return buffer.getvalue()


class ReplyAudio:
    def __init__(self):
        self.pcm = bytearray()
        self.done = asyncio.Event()
        self.failed = False
        self.rate = None
        self.resample_state = None

    async def send_json(self, payload):
        event = payload["type"]
        if self.done.is_set():
            return
        if event == "audio":
            rate = payload["sample_rate"]
            if rate != self.rate:
                self.rate = rate
                self.resample_state = None
            pcm, self.resample_state = audioop.ratecv(
                base64.b64decode(payload["audio_base64"]), 2, 1, rate, 16000,
                self.resample_state,
            )
            if len(self.pcm) + len(pcm) > MAX_PCM_BYTES:
                self.failed = True
                self.done.set()
            else:
                self.pcm.extend(pcm)
        elif event in ("error", "interrupted", "closed"):
            self.failed = True
            self.done.set()
        elif event == "state" and payload.get("state") == "listening" and self.pcm:
            self.done.set()


async def process_round(session_no: str, pcm: bytes, result: DeviceRound):
    reply = ReplyAudio()
    session = None
    attached = False
    try:
        async with asyncio.timeout(120):
            task_id, patient_id, _, patient_info, scales = await asyncio.to_thread(
                _load_session, session_no, device=True
            )
            session = await voice_gateway.get_or_create(
                session_no=session_no, task_id=task_id, patient_id=patient_id,
                patient_info=patient_info, scale_codes=scales, manual_input=True,
            )
            if session.connected_clients or session.turn_detection == "server_vad":
                raise RuntimeError("语音会话正在使用")
            attached = True
            await voice_gateway.attach(session, reply)
            for start in range(0, len(pcm), 8192):
                await voice_gateway.append_audio(session, pcm[start:start + 8192])
            await voice_gateway.commit(session)
            await reply.done.wait()
            if reply.failed:
                raise RuntimeError("语音回复异常")
            result.wav = encode_wav(bytes(reply.pcm))
    except Exception as exc:
        logger.info("设备 HTTP 轮次失败，错误类型=%s", type(exc).__name__)
    finally:
        try:
            if attached:
                session.connected_clients.discard(reply)
                # 每轮重建模型连接，从落库历史恢复，丢弃未完成的上游缓冲。
                await voice_gateway.close(session_no)
        finally:
            if result.status == "processing":
                result.status = "ready" if result.wav is not None else "failed"
            result.expires = time.monotonic() + ROUND_TTL


def lookup_round(key):
    result = rounds.get(key)
    if result is not None and result.expires <= time.monotonic() and result.status != "processing":
        rounds.pop(key, None)
        return None
    return result


@router.put("/tasks/{task_no}/turns/{turn_id}", status_code=202)
async def upload(task_no: str, turn_id: str, request: Request, device_id: Device):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", turn_id) or len(task_no) > 64:
        raise HTTPException(422, "轮次编号无效")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
        raise HTTPException(415, "请上传原始 PCM")
    key = (device_id, task_no, turn_id)
    if lookup_round(key) is None:
        task = await asyncio.to_thread(current_task, device_id)
        if not task or task[0] != task_no or task[2] != "ready":
            raise HTTPException(409, "任务未分配或尚未就绪")
    body = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_PCM_BYTES:
                    raise HTTPException(413, "录音超过 60 秒")
                body.extend(chunk)
    except TimeoutError as exc:
        raise HTTPException(408, "上传超时") from exc
    if not body or len(body) % 2:
        raise HTTPException(422, "PCM 长度无效")
    digest = hashlib.sha256(body).hexdigest()
    result = lookup_round(key)
    if result:
        if result.digest != digest:
            raise HTTPException(409, "轮次编号已用于另一段录音")
        return {"turn_id": turn_id, "status": result.status}
    task = await asyncio.to_thread(current_task, device_id)
    if not task or task[0] != task_no or task[2] != "ready":
        raise HTTPException(409, "任务未分配或尚未就绪")
    for existing in list(rounds):
        lookup_round(existing)
    # 数据库查询会让出事件循环，因此写入前再次检查重复和并发。
    result = rounds.get(key)
    if result:
        if result.digest != digest:
            raise HTTPException(409, "轮次编号已用于另一段录音")
        return {"turn_id": turn_id, "status": result.status}
    if any(k[0] == device_id and r.status == "processing" for k, r in rounds.items()):
        raise HTTPException(409, "设备已有正在处理的录音")
    if len(rounds) >= MAX_ROUNDS:
        raise HTTPException(503, "录音处理繁忙")
    result = DeviceRound(digest, float("inf"))
    rounds[key] = result
    worker = asyncio.create_task(process_round(task[1], bytes(body), result))
    workers.add(worker)
    worker.add_done_callback(workers.discard)
    return {"turn_id": turn_id, "status": "processing"}


@router.get("/tasks/{task_no}/turns/{turn_id}")
async def status(task_no: str, turn_id: str, device_id: Device):
    result = lookup_round((device_id, task_no, turn_id))
    if result is None:
        raise HTTPException(404, "轮次不存在或已过期")
    return {"turn_id": turn_id, "status": result.status}


@router.get("/tasks/{task_no}/turns/{turn_id}/audio")
async def audio(task_no: str, turn_id: str, device_id: Device):
    result = lookup_round((device_id, task_no, turn_id))
    if result is None:
        raise HTTPException(404, "轮次不存在或已过期")
    if result.status != "ready" or result.wav is None:
        raise HTTPException(409, "回复音频不可用")
    return Response(result.wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


async def stop_workers():
    pending = list(workers)
    for worker in pending:
        worker.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    rounds.clear()
