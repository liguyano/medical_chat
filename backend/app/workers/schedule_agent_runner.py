"""Schedule Agent 单轮运行器
作用：按需创建调度 Agent，检查一条患者答案并发布下一轮约束。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel
from medagent.agents.factory import create_schedule_agent
from medagent.agents.service_agent.schedule_agent import ToolCallRecord
from sqlalchemy import select

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import base as model_base
from app.models.interaction import InteractionSession
from app.schemas.events import ConstraintEvent
from app.utils.redis_client import RedisClient
from app.workers.event_publisher import DialogEventPublisher
from app.workers.schedule_task_store import ScheduleTaskStore
from app.workers.worker_lease import WorkerLease

logger = logging.getLogger(__name__)


def decode_stream_fields(fields: Mapping[Any, Any]) -> dict[str, Any]:
    """解码 Redis Stream 字段。"""
    decoded: dict[str, Any] = {}
    for raw_key, raw_value in fields.items():
        key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
        value: Any = (
            raw_value.decode("utf-8") if isinstance(raw_value, bytes) else raw_value
        )
        if key in {"tool_calls", "metadata", "tool_args"} and isinstance(value, str):
            try:
                value = None if value == "None" else json.loads(value)
            except (TypeError, ValueError):
                logger.warning("Redis Stream JSON 字段解析失败: %s", key)
        decoded[key] = value
    return decoded


class ScheduleAgentRunner:
    """Schedule Agent 患者答案单轮执行器。"""

    def __init__(
        self,
        *,
        loader: AssessmentQuestionLoader,
        history_manager: DialogHistoryManager,
        redis_client: RedisClient,
        publisher_factory: Callable[[str], DialogEventPublisher],
        model: BaseChatModel,
        state_ttl: int = 86400,
    ) -> None:
        self.loader = loader
        self.history_manager = history_manager
        self.redis = redis_client
        self.publisher_factory = publisher_factory
        self.model = model
        self.state_ttl = state_ttl

    async def run(
        self,
        session_id: str,
        *,
        scale_codes: list[str],
        source_message_id: str | None = None,
        source_event_id: str | None = None,
        check_interval: int = 1,
        patient_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """准备 Task-todo，或检查一条患者答案并发布非阻塞引导。"""
        if not scale_codes:
            return {"status": "failed", "reason": "missing_scale_codes"}

        questions = await self.loader.load_questions_by_scale_codes(scale_codes)
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}
        task_store = ScheduleTaskStore(self.redis, ttl=self.state_ttl)

        if not source_message_id:
            agent = create_schedule_agent(
                session_id=session_id,
                task_list=questions,
                model=self.model,
                check_interval=max(check_interval, 1),
            )
            plan = await agent.prepare_task_todo(patient_info or {})
            task_store.save_plan(plan)
            return {
                "status": "prepared",
                "session_id": session_id,
                "question_count": len(plan.tasks),
                "opening_guidance": plan.opening_guidance,
            }

        plan = task_store.get_plan(session_id)
        planned_questions = plan.tasks if plan is not None and plan.tasks else questions

        lease = WorkerLease(
            self.redis,
            agent_name="schedule_agent",
            session_id=session_id,
            work_id=source_message_id,
        )
        if not lease.acquire():
            return {
                "status": "already_running",
                "session_id": session_id,
                "source_message_id": source_message_id,
            }

        state_key = f"schedule_agent:state:{session_id}"
        try:
            state = self.redis.get(state_key)
            state = state if isinstance(state, dict) else {}
            processed = list(state.get("processed_message_ids") or [])
            if source_message_id in processed:
                return {
                    "status": "already_completed",
                    "session_id": session_id,
                    "source_message_id": source_message_id,
                }

            agent = create_schedule_agent(
                session_id=session_id,
                task_list=planned_questions,
                model=self.model,
                check_interval=max(check_interval, 1),
            )
            agent.restore_state(state)
            history = await self.history_manager.get_dialog_history(
                session_id,
                limit=40,
            )
            result = await agent.evaluate(
                self.history_manager.format_for_langchain(history),
                tool_calls=self._load_recent_tool_calls(session_id),
                force=True,
            )
            processed.append(source_message_id)
            saved_state = agent.dump_state()
            saved_state.update(
                {
                    "last_event_id": source_event_id or state.get("last_event_id") or "0-0",
                    "processed_message_ids": processed[-100:],
                }
            )
            if not self.redis.set(state_key, saved_state, ex=self.state_ttl):
                raise RuntimeError(f"Schedule Agent 状态保存失败: {state_key}")
            task_store.save_guidance(
                session_id,
                (
                    result.model_dump(mode="json")
                    if hasattr(result, "model_dump")
                    else dict(vars(result))
                ),
            )

            if result.is_deviation or result.missing_tool_calls:
                task_id = self._load_task_id(session_id)
                self.publisher_factory(session_id).publish(
                    ConstraintEvent(
                        session_id=session_id,
                        task_id=task_id,
                        constraint_type=(
                            "missing_tool"
                            if result.missing_tool_calls
                            else "deviation"
                        ),
                        constraint_prompt=result.constraint_prompt,
                        remaining_tasks=result.remaining_questions,
                    )
                )
            logger.info(
                "[Schedule Agent] 单轮完成: session=%s, source_message_id=%s, deviation=%s",
                session_id,
                source_message_id,
                result.is_deviation,
            )
            return {
                "status": "turn_completed",
                "session_id": session_id,
                "source_message_id": source_message_id,
                "is_deviation": result.is_deviation,
                "remaining_questions": result.remaining_questions,
            }
        finally:
            lease.release()

    def _load_task_id(self, session_id: str) -> int | None:
        """读取会话关联任务主键。"""
        if model_base.SessionLocal is None:
            return None
        with model_base.SessionLocal() as db:
            return db.scalar(
                select(InteractionSession.task_id).where(
                    InteractionSession.session_no == session_id,
                    InteractionSession.deleted == 0,
                )
            )

    def _load_recent_tool_calls(self, session_id: str) -> list[ToolCallRecord]:
        """从最近的 Agent 内部事件中恢复工具调用记录。"""
        try:
            messages = self.redis.xread(
                {f"dialog_stream:{session_id}": "0-0"},
                count=100,
                block=None,
            )
        except Exception:
            logger.exception("[Schedule Agent] 读取工具调用记录失败")
            return []
        calls: list[ToolCallRecord] = []
        for _, entries in messages:
            for _, raw_fields in entries:
                fields = decode_stream_fields(raw_fields)
                if fields.get("event_type") != "tool_call":
                    continue
                name = str(fields.get("tool_name") or "")
                if name:
                    calls.append(
                        ToolCallRecord(
                            name=name,
                            arguments=dict(fields.get("tool_args") or {}),
                        )
                    )
        return calls[-20:]
