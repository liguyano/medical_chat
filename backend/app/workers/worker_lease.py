"""Agent Worker Redis 租约
作用：标记指定会话的长驻 Worker 是否仍在消费，避免重复派发和空闲退出后无人恢复。
"""

from __future__ import annotations

import uuid

from app.utils.redis_client import RedisClient


class WorkerLease:
    """会话 Worker 租约
    作用：使用 Redis NX + TTL 保证同一 Agent、同一会话最多只有一个活动消费者。
    """

    def __init__(
        self,
        redis_client: RedisClient,
        *,
        agent_name: str,
        session_id: str,
        work_id: str = "session",
        ttl: int = 600,
    ) -> None:
        self.redis = redis_client
        self.key = f"{agent_name}:worker_lease:{session_id}:{work_id}"
        self.ttl = ttl
        self.token = uuid.uuid4().hex

    def acquire(self) -> bool:
        """尝试取得租约
        Return:
            - 是否取得成功；测试替身没有底层 Redis 时默认允许执行。
        """
        client = getattr(self.redis, "client", None)
        if client is None:
            return True
        return bool(client.set(self.key, self.token, ex=self.ttl, nx=True))

    def refresh(self) -> bool:
        """刷新租约 TTL
        Return:
            - 当前租约是否仍归属于本 Worker。
        """
        client = getattr(self.redis, "client", None)
        if client is None:
            return True
        current = client.get(self.key)
        if current not in (self.token, self.token.encode("utf-8")):
            return False
        return bool(client.expire(self.key, self.ttl))

    def release(self) -> None:
        """释放当前 Worker 租约"""
        client = getattr(self.redis, "client", None)
        if client is None:
            return
        client.eval(
            (
                "if redis.call('get', KEYS[1]) == ARGV[1] "
                "then return redis.call('del', KEYS[1]) else return 0 end"
            ),
            1,
            self.key,
            self.token,
        )
