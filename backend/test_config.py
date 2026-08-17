"""测试项目配置管理（config.yaml 加载、环境变量覆盖、日志初始化）"""
import sys
import os

# 设置UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append('.')


def test_load_config():
    """测试1: config.yaml 加载"""
    print("=== 测试1: 配置加载 ===")
    from app.configs.app_config import get_app_config

    cfg = get_app_config()
    print(f"✅ env={cfg.env}")
    print(f"✅ app={cfg.app.name}:{cfg.app.port}")
    print(f"✅ database={cfg.database.host}:{cfg.database.port}/{cfg.database.db}")
    print(f"✅ database.url={cfg.database.url}")
    print(f"✅ redis cache_url={cfg.redis.cache_url}")

    assert cfg.database.port == 15432, "数据库端口应为15432"
    assert cfg.database.user == "medical"
    print()
    return True


def test_celery_url_resolution():
    """测试2: Celery URL 自动拼装"""
    print("=== 测试2: Celery URL 解析 ===")
    from app.configs.app_config import get_app_config

    cfg = get_app_config()
    broker = cfg.resolved_celery_broker_url()
    backend = cfg.resolved_celery_backend_url()
    print(f"✅ broker={broker}")
    print(f"✅ backend={backend}")
    assert broker.endswith("/1"), "broker 应使用 db=1"
    assert backend.endswith("/2"), "backend 应使用 db=2"
    print()
    return True


def test_env_override():
    """测试3: 环境变量覆盖"""
    print("=== 测试3: 环境变量覆盖 ===")
    from app.configs import app_config

    # 清缓存后设置环境变量
    app_config.get_app_config.cache_clear()
    os.environ["APP_DATABASE__PASSWORD"] = "override_pwd_123"
    os.environ["APP_APP__PORT"] = "9999"
    try:
        cfg = app_config.get_app_config()
        print(f"✅ 覆盖后 database.password={cfg.database.password}")
        print(f"✅ 覆盖后 app.port={cfg.app.port}")
        assert cfg.database.password == "override_pwd_123"
        assert cfg.app.port == 9999
    finally:
        del os.environ["APP_DATABASE__PASSWORD"]
        del os.environ["APP_APP__PORT"]
        app_config.get_app_config.cache_clear()
    print()
    return True


def test_logging_setup():
    """测试4: 日志初始化"""
    print("=== 测试4: 日志系统 ===")
    import logging
    from app.configs.logging_config import setup_logging
    from app.configs.app_config import LoggingConfig

    setup_logging(LoggingConfig(level="DEBUG", json=False))
    logger = logging.getLogger("test.config")
    logger.info("日志系统初始化成功（文本格式）")

    setup_logging(LoggingConfig(level="INFO", json=True))
    logger.info("日志系统初始化成功（JSON格式）")
    print("✅ 日志系统初始化正常")
    print()
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("项目配置管理测试套件")
    print("=" * 60)
    print()

    ok = True
    ok = test_load_config() and ok
    ok = test_celery_url_resolution() and ok
    ok = test_env_override() and ok
    ok = test_logging_setup() and ok

    print("=" * 60)
    if ok:
        print("🎉 配置管理测试通过！")
    else:
        print("❌ 配置管理测试存在失败项")
    print("=" * 60)
    sys.exit(0 if ok else 1)
