"""Celery Beat启动脚本
作用：启动Celery Beat定时任务调度器。
使用方式：
    python -m app.celery_app.beat
    等同于: celery -A app.celery_app.celery_config:celery_app beat --loglevel=info
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.celery_app.celery_config import celery_app  # noqa: E402
import app.celery_app.tasks  # noqa: F401,E402  确保任务被导入注册


if __name__ == "__main__":
    celery_app.start(argv=[
        "beat",
        "--loglevel=info",
    ])
