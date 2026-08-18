"""Schedule Agent Task-todo 存储
作用：在 Redis 中保存可恢复的会话问诊计划和最近一次引导结果。
"""

from __future__ import annotations

from typing import Any

from medagent.agents.service_agent.schedule_agent import ScheduleTaskTodo
from pydantic import ValidationError

from app.utils.redis_client import RedisClient


class ScheduleTaskStore:
    """会话级 Task-todo 与引导缓存。"""

    def __init__(self, redis_client: RedisClient, *, ttl: int = 86400) -> None:
        self.redis = redis_client
        self.ttl = ttl

    @staticmethod
    def plan_key(session_id: str) -> str:
        return f"schedule_agent:task_todo:{session_id}"

    @staticmethod
    def guidance_key(session_id: str) -> str:
        return f"schedule_agent:guidance:{session_id}"

    def save_plan(self, plan: ScheduleTaskTodo) -> None:
        """保存 Task-todo。"""
        if not self.redis.set(
            self.plan_key(plan.session_id),
            plan.model_dump(mode="json"),
            ex=self.ttl,
        ):
            raise RuntimeError(f"Schedule Task-todo 保存失败: {plan.session_id}")

    def get_plan(self, session_id: str) -> ScheduleTaskTodo | None:
        """读取 Task-todo。"""
        payload = self.redis.get(self.plan_key(session_id))
        if not isinstance(payload, dict):
            return None
        try:
            return ScheduleTaskTodo.model_validate(payload)
        except ValidationError:
            return None

    def save_guidance(self, session_id: str, guidance: dict[str, Any]) -> None:
        """保存最近一次非阻塞调度建议。"""
        if not self.redis.set(
            self.guidance_key(session_id),
            guidance,
            ex=self.ttl,
        ):
            raise RuntimeError(f"Schedule 引导保存失败: {session_id}")

    def get_guidance(self, session_id: str) -> dict[str, Any]:
        """读取最近一次有效引导。"""
        payload = self.redis.get(self.guidance_key(session_id))
        return payload if isinstance(payload, dict) else {}
