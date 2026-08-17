"""Schedule Agent 后台运行器
作用：连接应用层数据库、Redis Stream、事件发布器与 medagent 调度智能体。
"""

import json
import logging
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models import BaseChatModel

from medagent.agents.factory import create_schedule_agent
from medagent.agents.service_agent.schedule_agent import ScheduleAgent, ToolCallRecord

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.schemas.events import ConstraintEvent, EventType, SessionEndEvent
from app.utils.redis_client import RedisClient
from app.workers.event_publisher import DialogEventPublisher

logger = logging.getLogger(__name__)


def decode_stream_fields(
    fields: Mapping[Any, Any],
) -> dict[str, Any]:
    """解码 Redis Stream 字段
    作用：统一处理 bytes、JSON 复杂字段和普通字符串。
    """
    decoded: dict[str, Any] = {}
    json_fields = {"tool_calls", "metadata"}
    for raw_key, raw_value in fields.items():
        key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
        value: Any = (
            raw_value.decode("utf-8")
            if isinstance(raw_value, bytes)
            else raw_value
        )
        if key in json_fields and isinstance(value, str):
            try:
                value = None if value == "None" else json.loads(value)
            except json.JSONDecodeError:
                logger.warning("Redis Stream JSON 字段解析失败: %s", key)
        decoded[key] = value
    return decoded


class ScheduleAgentRunner:
    """可注入依赖、可恢复状态的 Schedule Agent 事件循环。"""

    def __init__(
        self,
        *,
        loader: AssessmentQuestionLoader,
        history_manager: DialogHistoryManager,
        redis_client: RedisClient,
        publisher_factory: Callable[[str], DialogEventPublisher],
        model: BaseChatModel,
        block_ms: int = 5000,
        max_idle_reads: int = 60,
    ) -> None:
        """初始化运行器。"""
        self.loader = loader
        self.history_manager = history_manager
        self.redis = redis_client
        self.publisher_factory = publisher_factory
        self.model = model
        self.block_ms = block_ms
        self.max_idle_reads = max_idle_reads

    async def run(
        self,
        session_id: str,
        *,
        scale_codes: list[str],
        check_interval: int = 5,
    ) -> dict[str, Any]:
        """运行指定会话的调度循环。"""
        if not scale_codes:
            return {"status": "failed", "reason": "missing_scale_codes"}

        questions = await self.loader.load_questions_by_scale_codes(scale_codes)
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}

        agent = create_schedule_agent(
            session_id=session_id,
            task_list=questions,
            model=self.model,
            check_interval=check_interval,
        )
        state_key = f"schedule_agent:state:{session_id}"
        state = self.redis.get(state_key)
        if isinstance(state, dict):
            agent.restore_state(state)
        last_id = str(state.get("last_event_id", "0")) if isinstance(state, dict) else "0"

        recent_tool_calls: deque[ToolCallRecord] = deque(maxlen=50)
        stream_key = f"dialog_stream:{session_id}"
        idle_reads = 0
        started_at = datetime.now(UTC)

        while idle_reads < self.max_idle_reads:
            messages = self.redis.xread(
                {stream_key: last_id},
                count=10,
                block=self.block_ms,
            )
            if not messages:
                idle_reads += 1
                continue
            idle_reads = 0

            for _, message_list in messages:
                for raw_message_id, raw_fields in message_list:
                    message_id = (
                        raw_message_id.decode("utf-8")
                        if isinstance(raw_message_id, bytes)
                        else raw_message_id
                    )
                    last_id = str(message_id)
                    fields = decode_stream_fields(raw_fields)
                    if fields.get("event_type") != EventType.DIALOG_TURN.value:
                        self._save_state(state_key, agent, last_id)
                        continue

                    for call in fields.get("tool_calls") or []:
                        call_name = (
                            call.get("name") or call.get("tool_name")
                            if isinstance(call, dict)
                            else None
                        )
                        if call_name:
                            recent_tool_calls.append(
                                ToolCallRecord(
                                    name=call_name,
                                    arguments=(
                                        call.get("arguments")
                                        or call.get("tool_args")
                                        or {}
                                    ),
                                )
                            )

                    history = await self.history_manager.get_dialog_history(
                        session_id,
                        limit=30,
                    )
                    result = await agent.evaluate(
                        self.history_manager.format_for_langchain(history),
                        tool_calls=list(recent_tool_calls),
                    )
                    self._save_state(state_key, agent, last_id)

                    publisher = self.publisher_factory(session_id)
                    if result.is_deviation:
                        constraint_type = (
                            "missing_tool"
                            if result.missing_tool_calls
                            else "deviation"
                        )
                        publisher.publish(
                            ConstraintEvent(
                                session_id=session_id,
                                constraint_type=constraint_type,
                                constraint_prompt=result.constraint_prompt,
                                remaining_tasks=result.remaining_questions,
                            )
                        )

                    if not result.remaining_questions:
                        duration = int(
                            (datetime.now(UTC) - started_at).total_seconds()
                        )
                        publisher.publish(
                            SessionEndEvent(
                                session_id=session_id,
                                end_reason="completed",
                                total_turns=agent.turn_counter,
                                duration_seconds=duration,
                            )
                        )
                        return {
                            "status": "completed",
                            "session_id": session_id,
                            "turns": agent.turn_counter,
                        }

        return {
            "status": "idle_timeout",
            "session_id": session_id,
            "turns": agent.turn_counter,
        }

    def _save_state(
        self,
        state_key: str,
        agent: ScheduleAgent,
        last_event_id: str,
    ) -> None:
        """保存调度状态和最后消费位置，TTL 为一小时。"""
        state = agent.dump_state()
        state["last_event_id"] = last_event_id
        if not self.redis.set(state_key, state, ex=3600):
            raise RuntimeError(f"Schedule Agent 状态保存失败: {state_key}")
