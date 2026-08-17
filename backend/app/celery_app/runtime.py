"""Celery Worker 运行时基础设施初始化。

独立 Worker 不会经过 FastAPI 的启动生命周期，因此需要在 Worker 进程中
单独初始化数据库会话工厂和 Redis 客户端。
"""

from __future__ import annotations

import os
from threading import Lock

_initialized_pid: int | None = None
_initialization_lock = Lock()


def ensure_worker_runtime() -> None:
    """按操作系统进程幂等初始化数据库与 Redis。

    Celery prefork 子进程不能复用父进程的数据库连接池，因此以 PID 作为
    初始化边界。任务入口也会调用本函数，用于覆盖 Windows solo worker
    及未触发进程信号的嵌入式执行方式。
    """
    global _initialized_pid

    current_pid = os.getpid()
    if _initialized_pid == current_pid:
        return

    with _initialization_lock:
        if _initialized_pid == current_pid:
            return

        from app.configs.app_config import get_app_config
        from app.models.base import init_db
        from app.utils.redis_client import init_redis

        config = get_app_config()
        init_db(
            config.database.url,
            pool_size=config.database.pool_size,
            max_overflow=config.database.max_overflow,
            pool_pre_ping=config.database.pool_pre_ping,
            echo=config.database.echo,
        )
        init_redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.cache_db,
            password=config.redis.password,
        )
        _initialized_pid = current_pid
