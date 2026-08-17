"""Celery配置
作用：创建全局唯一的Celery应用实例，配置broker、backend、任务队列路由与定时任务。
说明：worker.py / beat.py / tasks.py 全部复用本模块的同一个 celery_app 实例，
      避免出现任务绑定到不同Celery实例导致Worker无法识别任务的问题。
"""
import logging

from celery import Celery
from celery.signals import worker_process_init
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)


@worker_process_init.connect
def _initialize_worker_process_runtime(**_kwargs) -> None:
    """在每个 Celery 执行进程中初始化数据库与 Redis。"""
    from app.celery_app.runtime import ensure_worker_runtime

    ensure_worker_runtime()


def _build_celery_app() -> Celery:
    """构建Celery应用实例
    作用：从全局配置读取broker/backend地址，完成全部Celery配置。
    Return:
        - app: 配置完成的Celery应用实例
    """
    # 从全局配置解析连接地址（支持 config.yaml 与 APP_* 环境变量覆盖）
    from app.configs.app_config import get_app_config

    cfg = get_app_config()
    broker_url = cfg.resolved_celery_broker_url()
    backend_url = cfg.resolved_celery_backend_url()

    app = Celery("medical_evaluate")

    # ==================== Broker和Backend配置 ====================
    app.conf.broker_url = broker_url
    app.conf.result_backend = backend_url
    app.conf.broker_connection_retry_on_startup = True  # 启动时重试连接

    # ==================== 任务序列化配置 ====================
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]
    app.conf.timezone = "Asia/Shanghai"
    app.conf.enable_utc = False

    # ==================== 任务结果配置 ====================
    app.conf.result_expires = 3600  # 结果过期时间：1小时
    app.conf.result_extended = True  # 扩展结果信息

    # ==================== 任务执行配置 ====================
    app.conf.task_acks_late = True  # 任务完成后才ACK（避免任务丢失）
    app.conf.task_reject_on_worker_lost = True  # Worker崩溃时拒绝任务
    app.conf.task_time_limit = cfg.celery.task_time_limit  # 任务硬超时（秒）
    app.conf.task_soft_time_limit = cfg.celery.task_soft_time_limit  # 任务软超时（秒）
    app.conf.worker_prefetch_multiplier = 1  # 每次只预取1个任务（避免任务堆积）
    app.conf.worker_max_tasks_per_child = 100  # 每个Worker进程最多执行100个任务后重启

    # ==================== 任务队列路由配置 ====================
    # 定义三个独立的队列：schedule、dialog、extraction，外加default
    app.conf.task_queues = (
        Queue(
            "schedule_queue",
            Exchange("schedule_exchange", type="direct"),
            routing_key="schedule",
            priority=10,  # 高优先级（Schedule Agent需要快速响应）
        ),
        Queue(
            "dialog_queue",
            Exchange("dialog_exchange", type="direct"),
            routing_key="dialog",
            priority=8,  # 中高优先级（对话需要实时响应）
        ),
        Queue(
            "extraction_queue",
            Exchange("extraction_exchange", type="direct"),
            routing_key="extraction",
            priority=5,  # 中等优先级（字段抽取可以稍微延迟）
        ),
        Queue(
            "default",
            Exchange("default", type="direct"),
            routing_key="default",
            priority=1,  # 默认低优先级
        ),
    )
    app.conf.task_default_queue = "default"
    app.conf.task_default_exchange = "default"
    app.conf.task_default_routing_key = "default"

    # 任务路由规则
    app.conf.task_routes = {
        "app.celery_app.tasks.schedule_agent_worker": {
            "queue": "schedule_queue",
            "routing_key": "schedule",
        },
        "app.celery_app.tasks.dialog_agent_preheat": {
            "queue": "dialog_queue",
            "routing_key": "dialog",
        },
        "app.celery_app.tasks.extraction_agent_worker": {
            "queue": "extraction_queue",
            "routing_key": "extraction",
        },
    }

    # ==================== Beat定时任务配置 ====================
    app.conf.beat_schedule = {
        # 每5分钟清理一次过期会话
        "cleanup-expired-sessions": {
            "task": "app.celery_app.tasks.cleanup_expired_sessions",
            "schedule": 300.0,  # 300秒 = 5分钟
        },
    }

    # ==================== 日志配置 ====================
    app.conf.worker_hijack_root_logger = False  # 不劫持根日志
    app.conf.worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
    app.conf.worker_task_log_format = (
        "[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s"
    )

    # 自动发现任务（导入tasks模块，触发任务注册到本实例）
    app.autodiscover_tasks(["app.celery_app"])

    logger.info("Celery应用配置完成: broker=%s, backend=%s", broker_url, backend_url)
    return app


# 全局唯一的Celery实例（模块导入时创建，worker/beat/tasks共用）
celery_app: Celery = _build_celery_app()
