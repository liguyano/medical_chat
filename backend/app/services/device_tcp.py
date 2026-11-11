"""嵌入式设备原生 TCP 接入。"""

import asyncio
import audioop
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import struct

from fastapi import HTTPException
from sqlalchemy import select

from app.models import base
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask

logger = logging.getLogger(__name__)
HEADER = struct.Struct("!BI")
CONTROL, AUDIO = 1, 2
MAX_FRAME = 8192
connections = {}


def registered_devices():
    devices = json.loads(os.getenv("DEVICE_TCP_CREDENTIALS", "{}"))
    if not isinstance(devices, dict) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
        for device_id, digest in devices.items()
    ):
        raise ValueError("DEVICE_TCP_CREDENTIALS 配置无效")
    return devices


def check_device_available(db, device_id):
    if device_id not in registered_devices():
        raise HTTPException(422, "设备未登记")
    if db.scalar(select(CareTask.id).where(
        CareTask.device_id == device_id,
        CareTask.deleted == 0,
        CareTask.task_status.in_(("pending", "in_progress", "pending_review")),
    )) is not None:
        raise HTTPException(409, "设备已有评估任务")


def current_task(device_id):
    with base.SessionLocal() as db:
        return db.execute(
            select(CareTask.task_no, InteractionSession.session_no, CareTask.preparation_status)
            .join(InteractionSession, InteractionSession.task_id == CareTask.id)
            .where(
                CareTask.device_id == device_id,
                CareTask.collection_mode == "embedded_device",
                CareTask.deleted == 0,
                CareTask.task_status == "in_progress",
                InteractionSession.deleted == 0,
                InteractionSession.session_status.in_(("pending", "active")),
            )
            .order_by(InteractionSession.id.desc())
            .limit(1)
        ).first()


async def read_frame(reader):
    async with asyncio.timeout(45):
        kind, length = HEADER.unpack(await reader.readexactly(HEADER.size))
        if kind not in (CONTROL, AUDIO) or not 0 < length <= MAX_FRAME:
            raise ValueError("invalid frame")
        return kind, await reader.readexactly(length)


class DeviceOutput:
    def __init__(self, writer):
        self.writer = writer
        self.lock = asyncio.Lock()
        self.playing = False
        self.busy = False
        self.rate_state = None
        self.rate = None

    async def send(self, kind, payload):
        self.writer.write(HEADER.pack(kind, len(payload)) + payload)
        try:
            await asyncio.wait_for(self.writer.drain(), 5)
        except (ConnectionError, TimeoutError) as exc:
            self.writer.close()
            raise RuntimeError("设备连接不可写") from exc

    async def control(self, event, **fields):
        await self.send(CONTROL, json.dumps({"type": event, **fields}).encode())

    async def send_json(self, payload):
        async with self.lock:
            if payload["type"] == "audio":
                rate = payload["sample_rate"]
                if not self.playing:
                    self.playing = True
                    self.busy = True
                    await self.control("PLAY_START", sample_rate=16000)
                if self.rate != rate:
                    self.rate_state = None
                    self.rate = rate
                pcm, self.rate_state = audioop.ratecv(
                    base64.b64decode(payload["audio_base64"]),
                    2, 1, rate, 16000, self.rate_state,
                )
                for offset in range(0, len(pcm), MAX_FRAME):
                    await self.send(AUDIO, pcm[offset:offset + MAX_FRAME])
            elif payload["type"] == "closed" or (
                payload["type"] == "state" and payload.get("state") == "listening"
            ):
                self.busy = False
                if self.playing:
                    self.playing = False
                    self.rate_state = None
                    await self.control("PLAY_END")
                if payload["type"] == "closed":
                    self.writer.close()
            elif payload["type"] == "error":
                await self.control("ERROR", code="VOICE_ERROR")


async def handle_device(reader, writer):
    from app.api.voice_dialog import _load_session
    from app.services.voice_gateway import voice_gateway

    output = DeviceOutput(writer)
    device_id = None
    session = None
    attached = False
    recording = False
    try:
        kind, body = await read_frame(reader)
        hello = json.loads(body) if kind == CONTROL else {}
        if not isinstance(hello, dict) or hello.get("type") != "HELLO" or hello.get("version") != 1:
            raise ValueError("invalid handshake")
        device_id = hello.get("device_id")
        secret = hello.get("secret")
        if not isinstance(device_id, str) or not isinstance(secret, str):
            raise ValueError("invalid credentials")
        expected = registered_devices().get(device_id)
        if not isinstance(expected, str) or not hmac.compare_digest(
            hashlib.sha256(secret.encode()).hexdigest(), expected
        ):
            raise ValueError("invalid credentials")
        if device_id in connections:
            await output.control("ERROR", code="DEVICE_CONNECTED")
            return
        connections[device_id] = writer
        await output.control("HELLO_OK")
        while True:
            kind, body = await read_frame(reader)
            if kind == AUDIO:
                if not recording or len(body) % 2:
                    raise ValueError("unexpected audio")
                await voice_gateway.append_audio(session, body)
                continue
            control = json.loads(body)
            if not isinstance(control, dict):
                raise ValueError("invalid control")
            event = control.get("type")
            if event == "PING":
                await output.control("PONG")
            elif event in ("GET_TASK", "START"):
                assignment = await asyncio.to_thread(current_task, device_id)
                if event == "GET_TASK":
                    await output.control(
                        "TASK", task_no=assignment[0] if assignment else None,
                        ready=bool(assignment and assignment[2] == "ready"),
                    )
                elif not assignment or assignment[2] != "ready":
                    await output.control("ERROR", code="TASK_NOT_READY")
                elif session is not None and not session.closed and session.session_no == assignment[1]:
                    await output.control("STARTED")
                else:
                    if session is not None and attached:
                        session.connected_clients.discard(output)
                        attached = False
                        await voice_gateway.close(session.session_no)
                    _, session_no, _ = assignment
                    task_id, patient_id, _, patient_info, scales = await asyncio.to_thread(
                        _load_session, session_no, device=True
                    )
                    session = await voice_gateway.get_or_create(
                        session_no=session_no, task_id=task_id, patient_id=patient_id,
                        patient_info=patient_info, scale_codes=scales, manual_input=True,
                    )
                    if session.connected_clients or session.turn_detection == "server_vad":
                        await output.control("ERROR", code="SESSION_BUSY")
                        break
                    attached = True
                    await voice_gateway.attach(session, output)
                    await output.control("STARTED")
            elif event == "RECORD_START" and session and not session.closed and not recording and not output.busy:
                assignment = await asyncio.to_thread(current_task, device_id)
                if not assignment or assignment[1] != session.session_no:
                    await output.control("ERROR", code="TASK_ENDED")
                    break
                recording = True
                await output.control("RECORDING")
            elif event == "RECORD_END" and recording:
                recording = False
                assignment = await asyncio.to_thread(current_task, device_id)
                if not assignment or assignment[1] != session.session_no:
                    await output.control("ERROR", code="TASK_ENDED")
                    break
                output.busy = True
                await voice_gateway.commit(session)
            else:
                await output.control("ERROR", code="INVALID_STATE")
    except (asyncio.IncompleteReadError, ConnectionError, TimeoutError):
        pass
    except Exception as exc:
        logger.info("设备 TCP 会话结束，错误类型=%s", type(exc).__name__)
        if not writer.is_closing():
            try:
                await output.control("ERROR", code="CONNECTION_FAILED")
            except RuntimeError:
                pass
    finally:
        try:
            if attached:
                session.connected_clients.discard(output)
                await voice_gateway.close(session.session_no)
        finally:
            if connections.get(device_id) is writer:
                connections.pop(device_id)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
