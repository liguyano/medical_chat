"""Dialog Agent 应用层依赖组装与 Redis 适配器
作用：提供 App 层依赖注入函数，组装 middlewares / state_store / history_store，
      供 SDK 工厂使用；封装 Redis 约束源和事件接收器。
说明：
  - get_runtime_dependencies() 返回依赖字典，传递给 create_dialog_agent()；
  - Dialog Agent 实例统一由 medagent 工厂创建。
"""

from __future__ import annotations

from typing import Any

from medagent.agents.middlewares import (
    EventPublishMiddleware,
    ScheduleConstraintMiddleware,
    TimeoutMiddleware,
)

from app.managers.agent_state_manager import AsyncAgentStateManager
from app.managers.dialog_history_manager import DialogHistoryManager
from app.managers.session_timeout_manager import SessionTimeoutManager
from app.schemas.events import DialogTurnEvent, EventType, ToolCallEvent
from app.services.dialog_tool_executor import execute_tool
from app.utils.redis_client import RedisClient
from app.workers.event_publisher import DialogEventPublisher


def _decode(value: Any) -> Any:
    """将 Redis bytes 转换为 UTF-8 文本。"""
    return value.decode("utf-8") if isinstance(value, bytes) else value


class RedisConstraintSource:
    """从统一 dialog_stream 消费尚未处理的 ConstraintEvent。"""

    def __init__(self, redis_client: RedisClient, *, state_ttl: int = 3600) -> None:
        self.redis = redis_client
        self.state_ttl = state_ttl

    def __call__(self, session_id: str) -> list[str]:
        cursor_key = f"dialog_agent:constraint_cursor:{session_id}"
        saved_cursor = self.redis.get(cursor_key)
        last_id = str(saved_cursor) if saved_cursor else "0"
        messages = self.redis.xread(
            {f"dialog_stream:{session_id}": last_id},
            count=100,
            block=None,
        )
        constraints: list[str] = []
        latest_id = last_id
        for _, entries in messages:
            for raw_id, raw_fields in entries:
                latest_id = str(_decode(raw_id))
                fields = {_decode(key): _decode(value) for key, value in raw_fields.items()}
                if fields.get("event_type") != EventType.CONSTRAINT.value:
                    continue
                prompt = str(fields.get("constraint_prompt") or "")
                if prompt and prompt not in constraints:
                    constraints.append(prompt)

        if latest_id != last_id and not self.redis.set(
            cursor_key,
            latest_id,
            ex=self.state_ttl,
        ):
            raise RuntimeError(f"Dialog Agent 约束游标保存失败: {cursor_key}")
        return constraints


class AppDialogEventSink:
    """将 SDK 轮次事件转换为 App 事件并写入统一 Stream。"""

    def __init__(
        self,
        session_id: str,
        publisher: DialogEventPublisher | None = None,
    ) -> None:
        self.publisher = publisher or DialogEventPublisher(session_id)

    def __call__(self, event: dict[str, Any]) -> None:
        """接收 SDK 事件并发布结构化事件。"""
        event_type = str(event.get("event_type") or "")
        session_id = str(event.get("session_id") or self.publisher.session_id or "")
        if event_type == EventType.DIALOG_TURN.value:
            self.publisher.publish(
                DialogTurnEvent(
                    session_id=session_id,
                    task_id=event.get("task_id"),
                    message_id=event.get("message_id"),
                    turn_number=int(event.get("turn_number") or 0),
                    question=str(event.get("question") or ""),
                    answer=str(event.get("answer") or ""),
                    tool_calls=event.get("tool_calls"),
                    metadata=event.get("metadata"),
                )
            )
        elif event_type == EventType.TOOL_CALL.value:
            tool_name = str(event.get("tool_name") or "")
            tool_args = dict(event.get("tool_args") or {})
            tool_result = event.get("tool_result")
            self.publisher.publish(
                ToolCallEvent(
                    session_id=session_id,
                    task_id=event.get("task_id"),
                    message_id=event.get("message_id"),
                    turn_number=int(event.get("turn_number") or 0),
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                )
            )
            from app.services.tool_interaction_service import publish_tool_result

            publish_tool_result(
                session_no=session_id,
                task_id=event.get("task_id"),
                message_no=event.get("message_id"),
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
                publisher=self.publisher,
            )


def get_runtime_dependencies(session_id: str) -> dict[str, Any]:
    """组装 Dialog Agent 运行时依赖（App 层注入）
    作用：返回 middlewares / state_store / history_store / tool_executor，
          供 create_dialog_agent() 使用。
    Args:
        - session_id: 会话 ID
    Return:
        - 包含 middlewares / state_store / history_store / tool_executor 的字典
    """
    from app.utils.redis_client import get_redis

    redis_client = get_redis()
    timeout_manager = SessionTimeoutManager()
    event_sink = AppDialogEventSink(
        session_id,
        DialogEventPublisher(session_id, redis_client),
    )

    return {
        "middlewares": [
            ScheduleConstraintMiddleware(RedisConstraintSource(redis_client)),
            EventPublishMiddleware(session_id, event_sink),
            TimeoutMiddleware(timeout_manager.update_activity),
        ],
        "state_store": AsyncAgentStateManager(),
        "history_store": DialogHistoryManager(),
        "tool_executor": execute_tool,
    }
