"""测试Celery任务队列功能
说明：
  - 连接测试与路由测试不依赖Worker；
  - 任务执行测试需要先启动Worker（python -m app.celery_app.worker），
    未检测到活跃Worker时自动跳过，避免阻塞。
"""
import sys
import os

# 设置UTF-8编码（Windows兼容）
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append('.')

from app.celery_app.celery_config import celery_app
from app.celery_app.tasks import test_task


def _has_active_worker() -> bool:
    """检测是否存在活跃的Celery Worker"""
    try:
        active = celery_app.control.inspect().active()
        return bool(active)
    except Exception:
        return False


def test_broker_connection():
    """测试1: Broker连接测试"""
    print("=== 测试1: Broker连接测试 ===")
    try:
        conn = celery_app.connection()
        conn.ensure_connection(max_retries=3, timeout=5)
        conn.release()
        print("✅ Broker连接成功")
    except Exception as e:
        print(f"❌ Broker连接失败: {e}")
        return False
    print()
    return True


def test_task_routing():
    """测试2: 任务路由测试"""
    print("=== 测试2: 任务路由测试 ===")

    queues = celery_app.conf.task_queues
    print(f"✅ 已配置 {len(queues)} 个队列:")
    for queue in queues:
        print(f"   - {queue.name} (routing_key={queue.routing_key})")

    routes = celery_app.conf.task_routes
    print(f"\n✅ 已配置 {len(routes)} 条路由规则:")
    for task_name, route_config in routes.items():
        print(f"   - {task_name}")
        print(f"     → queue={route_config['queue']}, routing_key={route_config['routing_key']}")

    # 校验任务已注册到实例
    registered = set(celery_app.tasks.keys())
    expected = {
        "app.celery_app.tasks.schedule_agent_worker",
        "app.celery_app.tasks.dialog_agent_preheat",
        "app.celery_app.tasks.extraction_agent_worker",
        "app.celery_app.tasks.cleanup_expired_sessions",
        "app.celery_app.tasks.test_task",
    }
    missing = expected - registered
    if missing:
        print(f"❌ 缺失任务注册: {missing}")
        return False
    print(f"\n✅ 5个任务已全部注册到celery_app实例")
    print()
    return True


def test_task_submission():
    """测试3: 任务提交与执行测试（需要Worker）"""
    print("=== 测试3: 任务提交与执行测试 ===")

    if not _has_active_worker():
        print("⚠️  未检测到活跃Worker，跳过执行测试")
        print("   提示: 另开终端运行: uv run python -m app.celery_app.worker")
        print()
        return True

    try:
        result = test_task.apply_async(args=[10, 20], queue="default")
        print(f"✅ 任务已提交: task_id={result.id}")
        task_result = result.get(timeout=10)
        assert task_result == 30, f"结果错误: {task_result}"
        print(f"✅ 任务执行成功: 10 + 20 = {task_result}")
    except Exception as e:
        print(f"❌ 任务执行失败: {e}")
        return False
    print()
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Celery测试套件")
    print("=" * 60)
    print()

    ok = True
    ok = test_broker_connection() and ok
    ok = test_task_routing() and ok
    ok = test_task_submission() and ok

    print("=" * 60)
    if ok:
        print("🎉 Celery配置测试通过！")
    else:
        print("❌ Celery配置测试存在失败项")
    print("=" * 60)
    sys.exit(0 if ok else 1)
