"""Dialog 模型输出快照
作用：在模型流式生成期间保存完整文本快照，供 SSE 断线恢复和任务重试使用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.utils.redis_client import RedisClient


class DialogOutputStore:
    """Dialog 输出快照存储器
    作用：维护单条 AI 消息的 streaming、completed、failed 状态和完整文本。
    """

    def __init__(self, redis_client: RedisClient, *, ttl: int = 86400) -> None:
        self.redis = redis_client
        self.ttl = ttl

    @staticmethod
    def output_key(session_id: str, message_id: str) -> str:
        """生成单条输出快照键。"""
        return f"dialog:output:{session_id}:{message_id}"

    @staticmethod
    def latest_key(session_id: str) -> str:
        """生成会话最新输出快照键。"""
        return f"dialog:output:latest:{session_id}"

    def get(self, session_id: str, message_id: str) -> dict[str, Any] | None:
        """读取指定 AI 消息快照。"""
        value = self.redis.get(self.output_key(session_id, message_id))
        return value if isinstance(value, dict) else None

    def get_latest(self, session_id: str) -> dict[str, Any] | None:
        """读取会话最新 AI 输出快照。"""
        value = self.redis.get(self.latest_key(session_id))
        return value if isinstance(value, dict) else None

    def start(
        self,
        *,
        session_id: str,
        task_id: int | str,
        message_id: str,
        generation_id: str,
        turn_number: int,
        question_id: int | str | None,
    ) -> dict[str, Any]:
        """初始化模型输出快照。"""
        snapshot = {
            "session_id": session_id,
            "task_id": task_id,
            "message_id": message_id,
            "generation_id": generation_id,
            "turn_number": turn_number,
            "question_id": str(question_id) if question_id is not None else None,
            "status": "streaming",
            "content": "",
            "last_event_id": None,
            "error_code": None,
            "error_message": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._save(snapshot)
        return snapshot

    def append(
        self,
        *,
        session_id: str,
        message_id: str,
        text_chunk: str,
        last_event_id: str | None = None,
    ) -> dict[str, Any]:
        """追加文本增量并刷新完整快照。"""
        snapshot = self.get(session_id, message_id)
        if snapshot is None:
            raise RuntimeError(f"Dialog 输出快照不存在: {session_id}/{message_id}")
        snapshot["status"] = "streaming"
        snapshot["content"] = f"{snapshot.get('content', '')}{text_chunk}"
        if last_event_id:
            snapshot["last_event_id"] = last_event_id
        snapshot["updated_at"] = datetime.now(UTC).isoformat()
        self._save(snapshot)
        return snapshot

    def complete(
        self,
        *,
        session_id: str,
        message_id: str,
        content: str,
        last_event_id: str | None,
    ) -> dict[str, Any]:
        """标记模型输出完成。"""
        snapshot = self.get(session_id, message_id)
        if snapshot is None:
            raise RuntimeError(f"Dialog 输出快照不存在: {session_id}/{message_id}")
        snapshot.update(
            {
                "status": "completed",
                "content": content,
                "last_event_id": last_event_id or snapshot.get("last_event_id"),
                "error_code": None,
                "error_message": None,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        self._save(snapshot)
        return snapshot

    def fail(
        self,
        *,
        session_id: str,
        message_id: str,
        error_code: str,
        error_message: str,
        last_event_id: str | None = None,
    ) -> dict[str, Any]:
        """标记模型输出失败，保留已生成文本用于排障和重试。"""
        snapshot = self.get(session_id, message_id)
        if snapshot is None:
            raise RuntimeError(f"Dialog 输出快照不存在: {session_id}/{message_id}")
        snapshot.update(
            {
                "status": "failed",
                "last_event_id": last_event_id or snapshot.get("last_event_id"),
                "error_code": error_code,
                "error_message": error_message,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        self._save(snapshot)
        return snapshot

    def _save(self, snapshot: dict[str, Any]) -> None:
        """同时保存消息快照和会话最新快照。"""
        session_id = str(snapshot["session_id"])
        message_id = str(snapshot["message_id"])
        if not self.redis.set(
            self.output_key(session_id, message_id),
            snapshot,
            ex=self.ttl,
        ):
            raise RuntimeError(f"Dialog 输出快照保存失败: {session_id}/{message_id}")
        if not self.redis.set(self.latest_key(session_id), snapshot, ex=self.ttl):
            raise RuntimeError(f"Dialog 最新输出快照保存失败: {session_id}")
