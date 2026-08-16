"""Celery Worker启动脚本
作用：启动Celery Worker进程，消费任务队列。
使用方式：
    python -m app.celery_app.worker
    等同于: celery -A app.celery_app.celery_config:celery_app worker --loglevel=info
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.celery_app.celery_config import celery_app  # noqa: E402
import app.celery_app.tasks  # noqa: F401,E402  确保任务被导入注册


if __name__ == "__main__":
    # Windows 下 prefork 池不可用，使用 solo/threads 池
    pool = "solo" if sys.platform == "win32" else "prefork"
    celery_app.worker_main(argv=[
        "worker",
        "--loglevel=info",
        f"--pool={pool}",
        "--queues=schedule_queue,dialog_queue,extraction_queue,default",
        "--hostname=worker@%h",
    ])
