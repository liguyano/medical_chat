"""SSE 消息格式化服务
作用：将 Redis Stream 中的事件消息转换为 SSE 事件（event / data / id），
      并提供 dialog_stream 的异步消费生成器，供 SSE 端点使用。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from redis.exceptions import RedisError

from app.schemas.events import EventType
from app.utils.redis_client import get_async_redis

logger = logging.getLogger(__name__)

# 心跳间隔（秒）：空闲时定期发送 ping 事件保活
HEARTBEAT_INTERVAL = 30

# 事件类型 -> SSE event 名称映射（对齐前端 SseEventType）
_EVENT_NAME_MAP: dict[str, str] = {
    # 核心事件（第一期）
    EventType.DIALOG_MESSAGE.value: "assistant_message_completed",
    EventType.ASSISTANT_MESSAGE_STARTED.value: "assistant_message_started",
    EventType.PATIENT_ANSWER.value: "user_transcript_completed",
    EventType.EXTRACTION_RESULT.value: "extraction_updated",
    EventType.PROGRESS_UPDATED.value: "progress_updated",
    EventType.SESSION_END.value: "task_status_updated",
    EventType.AGENT_ERROR.value: "error",
    EventType.EDUCATION_TRIGGERED.value: "education_triggered",
    EventType.EDUCATION_STATUS_UPDATED.value: "education_status_updated",
    EventType.CONSENT_TRIGGERED.value: "consent_triggered",
    EventType.CONSENT_STATUS_UPDATED.value: "consent_status_updated",
    EventType.HANDOFF_REQUESTED.value: "handoff_requested",
    EventType.HANDOFF_RESOLVED.value: "handoff_resolved",
    # 兼容旧事件（后补）
    EventType.DIALOG_TEXT.value: "assistant_text_delta",
    EventType.DIALOG_AUDIO.value: "assistant_audio_delta",
    EventType.SESSION_START.value: "session_status",
}


def dialog_stream_key(session_id: str) -> str:
    """对话流键名
    Args:
        - session_id: 会话内部 ID
    Return:
        - stream_key: dialog_stream:{session_id}
    """
    return f"dialog_stream:{session_id}"


def _decode_fields(fields: dict[bytes, bytes]) -> dict[str, Any]:
    """解码 Redis Stream 字段
    作用：将 bytes 键值解码为 str，并尝试还原 JSON 序列化的复杂字段。
    Args:
        - fields: Redis 返回的原始字段字典（bytes -> bytes）
    Return:
        - 解码后的字段字典（str -> Any）
    """
    result: dict[str, Any] = {}
    for raw_key, raw_value in fields.items():
        key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
        value = raw_value.decode("utf-8") if isinstance(raw_value, bytes) else raw_value
        # 尝试解析 JSON（dict/list 字段发布时被 json.dumps）
        if isinstance(value, str) and value and value[0] in "[{":
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                pass
        result[key] = value
    return result


def format_sse_event(message_id: str, fields: dict[bytes, bytes]) -> dict[str, str]:
    """将 Stream 消息格式化为 SSE 事件
    Args:
        - message_id: Redis Stream 消息 ID（作为 SSE id，用于断线重连）
        - fields: 原始字段字典
    Return:
        - EventSourceResponse 可消费的字典：{event, id, data}
    """
    data = _decode_fields(fields)
    event_type = str(data.get("event_type", ""))
    event_name = _EVENT_NAME_MAP.get(event_type, "heartbeat")

    # 构建前端预期的 SseEnvelope 格式
    envelope = {
        "event_id": message_id,
        "event_type": event_name,
        "task_id": data.get("task_id", ""),
        "session_id": data.get("session_id"),
        "message_id": data.get("message_id"),
        "occurred_at": data.get("timestamp", data.get("occurred_at", "")),
        "payload": _build_payload(event_type, data),
    }

    return {
        "event": event_name,
        "id": message_id,
        "data": json.dumps(envelope, ensure_ascii=False),
    }


def _build_payload(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """构建前端预期的 payload 字段
    作用：根据事件类型提取/转换字段，对齐前端 applyRealtimeEvent 消费逻辑。
    Args:
        - event_type: 后端事件类型（EventType 枚举值）
        - data: 解码后的事件字段
    Return:
        - payload 字典
    """
    if event_type == EventType.DIALOG_MESSAGE.value:
        # AI 问诊问题完成事件 -> assistant_message_completed
        return {
            "content_text": data.get("content", ""),
            "text": data.get("content", ""),
            "is_final": True,
            "turn_no": data.get("turn_number", 0),
            "question_id": data.get("question_id"),
            "role": "assistant",
            "cicare_stage": data.get("cicare_stage", "connect"),
        }
    elif event_type == EventType.DIALOG_TEXT.value:
        # 模型流式文本增量 -> assistant_text_delta
        return {
            "content_text": "",
            "delta": data.get("text_chunk", ""),
            "text": data.get("text_chunk", ""),
            "is_final": bool(data.get("is_final", False)),
            "turn_no": data.get("turn_number", 0),
            "question_id": data.get("question_id"),
            "role": "assistant",
        }
    elif event_type == EventType.ASSISTANT_MESSAGE_STARTED.value:
        return {
            "content_text": "",
            "delta": "",
            "text": "",
            "is_final": False,
            "turn_no": data.get("turn_number", 0),
            "question_id": data.get("question_id"),
            "generation_id": data.get("generation_id"),
            "role": "assistant",
        }
    elif event_type == EventType.PATIENT_ANSWER.value:
        # 患者答案事件 -> user_transcript_completed
        return {
            "content_text": data.get("content", ""),
            "text": data.get("content", ""),
            "turn_no": data.get("turn_number", 0),
            "role": "user",
            "client_message_id": data.get("client_message_id"),
        }
    elif event_type == EventType.EXTRACTION_RESULT.value:
        # 字段抽取结果 -> extraction_updated
        extracted_fields = data.get("extracted_fields", {})
        return {
            "fields": (
                list(extracted_fields.values())
                if isinstance(extracted_fields, dict)
                else extracted_fields
            ),
            "confidence_scores": data.get("confidence_scores", {}),
        }
    elif event_type == EventType.PROGRESS_UPDATED.value:
        return {
            "current": int(data.get("current", 0)),
            "total": int(data.get("total", 0)),
            "completed": bool(data.get("completed", False)),
            "remaining_question_ids": data.get("remaining_question_ids", []),
        }
    elif event_type == EventType.EDUCATION_TRIGGERED.value:
        return {
            "material_id": data.get("material_id", ""),
            "category": data.get("category", ""),
            "level": int(data.get("level", 2)),
            "document_version": data.get("document_version", ""),
            "title": data.get("title", "医学宣教"),
            "original_content": data.get("original_content", ""),
            "patient_content": data.get("patient_content", ""),
            "spoken_content": data.get("spoken_content", ""),
            "source_name": data.get("source_name"),
            "priority": data.get("priority", "medium"),
            "requires_acknowledgement": bool(
                data.get("requires_acknowledgement", True)
            ),
            "auto_play": bool(data.get("auto_play", True)),
        }
    elif event_type == EventType.EDUCATION_STATUS_UPDATED.value:
        return {
            "material_id": data.get("material_id", ""),
            "status": data.get("status", ""),
            "acknowledged": bool(data.get("acknowledged", False)),
        }
    elif event_type == EventType.CONSENT_TRIGGERED.value:
        return {
            "form_id": data.get("form_id", ""),
            "form_type": data.get("form_type", ""),
            "title": data.get("title", "知情同意确认"),
            "document_version": data.get("document_version", ""),
            "full_text": data.get("full_text", ""),
            "clauses": data.get("clauses", []),
            "status": data.get("status", "pending_signature"),
            "requires_signature": bool(data.get("requires_signature", True)),
            "auto_play": bool(data.get("auto_play", True)),
        }
    elif event_type == EventType.CONSENT_STATUS_UPDATED.value:
        return {
            "form_id": data.get("form_id", ""),
            "status": data.get("status", ""),
            "decision": data.get("decision", ""),
            "signature_file_url": data.get("signature_file_url"),
            "completed_at": data.get("completed_at"),
        }
    elif event_type == EventType.HANDOFF_REQUESTED.value:
        return {
            "request_id": data.get("request_id", ""),
            "reason": data.get("reason", ""),
            "requested_action": data.get("requested_action", "other"),
            "action_label": data.get("action_label", "人工护理操作"),
            "urgency": data.get("urgency", "routine"),
            "priority": data.get("priority", "high"),
            "title": data.get("title", "请求护士协助"),
            "description": data.get("description", data.get("reason", "")),
            "patient_name": data.get("patient_name", ""),
            "bed_no": data.get("bed_no"),
            "ward_name": data.get("ward_name"),
            "status": data.get("status", "requested"),
        }
    elif event_type == EventType.HANDOFF_RESOLVED.value:
        return {
            "request_id": data.get("request_id"),
            "status": data.get("status", "resolved"),
            "resolved_by": data.get("resolved_by"),
            "resolution": data.get("resolution"),
        }
    elif event_type in (EventType.TOOL_CALL.value, EventType.CONSTRAINT.value):
        return {
            "message": data.get("constraint_prompt") or data.get("tool_name", ""),
            "detail": data,
        }
    elif event_type == EventType.SESSION_END.value:
        # 会话结束 -> task_status_updated
        return {
            "task_status": "pending_review",
            "end_reason": data.get("end_reason", "completed"),
            "total_turns": data.get("total_turns", 0),
        }
    elif event_type == EventType.AGENT_ERROR.value:
        return {
            "agent_name": data.get("agent_name", ""),
            "error_code": data.get("error_code", "MODEL_CALL_FAILED"),
            "message": data.get("message", "AI 模型调用失败，请稍后重试"),
            "retrying": data.get("retrying", True),
        }
    else:
        # 其他事件保持原样
        return data


async def stream_dialog_events(
    session_id: str,
    last_event_id: str | None = None,
) -> AsyncGenerator[dict[str, str], None]:
    """消费 dialog_stream 并产出 SSE 事件
    作用：持续从 Redis Stream 阻塞读取新消息并格式化为 SSE 事件；空闲达到
          心跳间隔时产出 ping 事件保活。支持 Last-Event-ID 断线续读。
    Args:
        - session_id: 会话内部 ID
        - last_event_id: 续读起点消息 ID，None 时从连接后的新消息开始（"$"）
    Return:
        - 异步产出 SSE 事件字典
    """
    redis = get_async_redis()
    stream_key = dialog_stream_key(session_id)
    latest_snapshot = await redis.get(f"dialog:output:latest:{session_id}")
    snapshot_id = (
        str(latest_snapshot.get("last_event_id"))
        if isinstance(latest_snapshot, dict) and latest_snapshot.get("last_event_id")
        else None
    )
    if isinstance(latest_snapshot, dict):
        snapshot_event = _format_snapshot_event(latest_snapshot)
        if snapshot_event is not None:
            yield snapshot_event
    last_id = _max_stream_id(last_event_id or "0-0", snapshot_id or "0-0")

    while True:
        try:
            # 阻塞读取，block 单位毫秒；超时返回空列表触发心跳
            messages = await redis.xread(
                {stream_key: last_id},
                count=50,
                block=HEARTBEAT_INTERVAL * 1000,
            )
        except asyncio.CancelledError:
            # 客户端断开，正常退出
            logger.debug(f"SSE 消费取消: session={session_id}")
            raise
        except RedisError as e:
            logger.error(f"SSE 读取 Stream 失败: session={session_id} -> {e}")
            yield {"event": "error", "data": json.dumps({"message": "事件流读取失败"})}
            return

        if not messages:
            # 空闲，发送心跳
            yield {"event": "ping", "data": ""}
            continue

        for _stream_key, entries in messages:
            for raw_id, fields in entries:
                message_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
                last_id = message_id
                decoded = _decode_fields(fields)
                if decoded.get("event_type") in {
                    EventType.DIALOG_TURN.value,
                    EventType.TOOL_CALL.value,
                    EventType.CONSTRAINT.value,
                }:
                    continue
                yield format_sse_event(message_id, fields)


async def stream_nurse_events(
    staff_id: int | str,
    last_event_id: str | None = None,
) -> AsyncGenerator[dict[str, str], None]:
    """消费责任护士全局提醒流
    作用：让医护端在任意页面实时收到所负责患者的呼叫和处理状态。
    """
    redis = get_async_redis()
    stream_key = f"nurse_stream:{staff_id}"
    last_id = last_event_id or "0-0"
    while True:
        try:
            messages = await redis.xread(
                {stream_key: last_id},
                count=50,
                block=HEARTBEAT_INTERVAL * 1000,
            )
        except asyncio.CancelledError:
            raise
        except RedisError as exc:
            logger.error("SSE 读取护士提醒流失败: staff=%s -> %s", staff_id, exc)
            yield {
                "event": "error",
                "data": json.dumps({"message": "护士提醒流读取失败"}),
            }
            return
        if not messages:
            yield {"event": "ping", "data": ""}
            continue
        for _, entries in messages:
            for raw_id, fields in entries:
                message_id = (
                    raw_id.decode("utf-8")
                    if isinstance(raw_id, bytes)
                    else str(raw_id)
                )
                last_id = message_id
                yield format_sse_event(message_id, fields)


def _max_stream_id(left: str, right: str) -> str:
    """比较 Redis Stream ID，避免快照回放后重复消费旧增量。"""
    try:
        left_pair = tuple(int(part) for part in left.split("-", 1))
        right_pair = tuple(int(part) for part in right.split("-", 1))
        return left if left_pair >= right_pair else right
    except (TypeError, ValueError):
        return left or right


def _format_snapshot_event(snapshot: dict[str, Any]) -> dict[str, str] | None:
    """将 Redis 完整文本快照转换为一次可幂等应用的 SSE 事件。"""
    status = str(snapshot.get("status") or "")
    if status not in {"streaming", "completed", "failed"}:
        return None
    if status == "failed":
        event_name = "error"
        payload = {
            "agent_name": "dialog_agent",
            "error_code": snapshot.get("error_code") or "MODEL_CALL_FAILED",
            "message": snapshot.get("error_message")
            or "AI 模型调用失败，请稍后重试",
            "retrying": True,
        }
    elif status == "completed":
        event_name = "assistant_message_completed"
        payload = {
            "content_text": snapshot.get("content", ""),
            "text": snapshot.get("content", ""),
            "snapshot": True,
            "is_final": True,
            "turn_no": snapshot.get("turn_number", 0),
            "question_id": snapshot.get("question_id"),
            "role": "assistant",
        }
    else:
        event_name = "assistant_text_delta"
        payload = {
            "content_text": snapshot.get("content", ""),
            "delta": snapshot.get("content", ""),
            "text": snapshot.get("content", ""),
            "snapshot": True,
            "is_final": False,
            "turn_no": snapshot.get("turn_number", 0),
            "question_id": snapshot.get("question_id"),
            "role": "assistant",
            "generation_id": snapshot.get("generation_id"),
        }
    envelope = {
        "event_id": f"snapshot:{snapshot.get('generation_id', '')}",
        "event_type": event_name,
        "task_id": str(snapshot.get("task_id", "")),
        "session_id": snapshot.get("session_id"),
        "message_id": snapshot.get("message_id"),
        "occurred_at": snapshot.get("updated_at", ""),
        "payload": payload,
    }
    return {
        "event": event_name,
        "data": json.dumps(envelope, ensure_ascii=False),
    }
