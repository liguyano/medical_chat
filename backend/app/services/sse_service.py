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

from app.schemas.events import EventType
from app.utils.redis_client import get_async_redis

logger = logging.getLogger(__name__)

# 心跳间隔（秒）：空闲时定期发送 ping 事件保活
HEARTBEAT_INTERVAL = 30

# 事件类型 -> SSE event 名称映射（对齐前端 SseEventType）
_EVENT_NAME_MAP: dict[str, str] = {
    # 核心事件（第一期）
    EventType.DIALOG_MESSAGE.value: "assistant_text_delta",
    EventType.PATIENT_ANSWER.value: "user_transcript_completed",
    EventType.EXTRACTION_RESULT.value: "extraction_updated",
    EventType.TOOL_CALL.value: "progress_updated",
    EventType.CONSTRAINT.value: "progress_updated",
    EventType.SESSION_END.value: "task_status_updated",
    # 兼容旧事件（后补）
    EventType.DIALOG_TURN.value: "assistant_text_delta",
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
        # AI 问诊问题事件 -> assistant_text_delta
        return {
            "content_text": data.get("content", ""),
            "delta": data.get("content", ""),
            "text": data.get("content", ""),
            "turn_no": data.get("turn_number", 0),
            "question_id": data.get("question_id"),
            "role": "assistant",
            "cicare_stage": data.get("cicare_stage", "connect"),
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
        return {
            "fields": data.get("extracted_fields", {}),
            "confidence_scores": data.get("confidence_scores", {}),
        }
    elif event_type in (EventType.TOOL_CALL.value, EventType.CONSTRAINT.value):
        # 工具调用/约束事件 -> progress_updated
        return {
            "message": data.get("constraint_prompt") or data.get("tool_name", ""),
            "detail": data,
        }
    elif event_type == EventType.SESSION_END.value:
        # 会话结束 -> task_status_updated
        return {
            "status": "completed",
            "end_reason": data.get("end_reason", "completed"),
            "total_turns": data.get("total_turns", 0),
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
    # last_id="$" 表示只读连接建立后的新消息；带 Last-Event-ID 时从该 ID 之后续读
    last_id = last_event_id or "$"

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
        except Exception as e:
            logger.error(f"SSE 读取 Stream 失败: session={session_id} -> {e}")
            yield {"event": "error", "data": json.dumps({"message": "事件流读取失败"})}
            return

        if not messages:
            # 空闲，发送心跳
            yield {"event": "ping", "data": ""}
            continue

        for _stream_key, entries in messages:
            for raw_id, fields in entries:
                message_id = (
                    raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
                )
                last_id = message_id
                yield format_sse_event(message_id, fields)
