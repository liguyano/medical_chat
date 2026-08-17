"""Celery Worker 运行时初始化测试。"""

from types import SimpleNamespace
from unittest.mock import Mock


def runtime_config():
    """构造数据库与 Redis 测试配置。"""
    return SimpleNamespace(
        database=SimpleNamespace(
            url="postgresql://user:password@db:5432/app",
            pool_size=8,
            max_overflow=12,
            pool_pre_ping=True,
            echo=False,
        ),
        redis=SimpleNamespace(
            host="redis",
            port=6380,
            cache_db=4,
            password="secret",
        ),
    )


def test_worker_runtime_initializes_infrastructure_once_per_process(monkeypatch):
    """同一 Worker 进程重复调用时只初始化一次。"""
    import app.celery_app.runtime as runtime_module
    import app.configs.app_config as config_module
    import app.models.base as base_module
    import app.utils.redis_client as redis_module

    init_db = Mock()
    init_redis = Mock()
    monkeypatch.setattr(runtime_module, "_initialized_pid", None)
    monkeypatch.setattr(runtime_module.os, "getpid", lambda: 1001)
    monkeypatch.setattr(config_module, "get_app_config", runtime_config)
    monkeypatch.setattr(base_module, "init_db", init_db)
    monkeypatch.setattr(redis_module, "init_redis", init_redis)

    runtime_module.ensure_worker_runtime()
    runtime_module.ensure_worker_runtime()

    init_db.assert_called_once_with(
        "postgresql://user:password@db:5432/app",
        pool_size=8,
        max_overflow=12,
        pool_pre_ping=True,
        echo=False,
    )
    init_redis.assert_called_once_with(
        host="redis",
        port=6380,
        db=4,
        password="secret",
    )


def test_worker_runtime_reinitializes_after_process_change(monkeypatch):
    """prefork 子进程 PID 变化后必须重新创建进程内基础设施。"""
    import app.celery_app.runtime as runtime_module
    import app.configs.app_config as config_module
    import app.models.base as base_module
    import app.utils.redis_client as redis_module

    current_pid = {"value": 1001}
    init_db = Mock()
    init_redis = Mock()
    monkeypatch.setattr(runtime_module, "_initialized_pid", None)
    monkeypatch.setattr(runtime_module.os, "getpid", lambda: current_pid["value"])
    monkeypatch.setattr(config_module, "get_app_config", runtime_config)
    monkeypatch.setattr(base_module, "init_db", init_db)
    monkeypatch.setattr(redis_module, "init_redis", init_redis)

    runtime_module.ensure_worker_runtime()
    current_pid["value"] = 1002
    runtime_module.ensure_worker_runtime()

    assert init_db.call_count == 2
    assert init_redis.call_count == 2


def test_worker_process_signal_initializes_runtime(monkeypatch):
    """Celery worker_process_init 信号应调用统一初始化入口。"""
    import app.celery_app.celery_config as celery_module
    import app.celery_app.runtime as runtime_module

    initializer = Mock()
    monkeypatch.setattr(runtime_module, "ensure_worker_runtime", initializer)

    celery_module._initialize_worker_process_runtime()

    initializer.assert_called_once_with()
