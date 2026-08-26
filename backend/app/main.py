"""FastAPI 应用入口
作用：创建 FastAPI 实例、配置 CORS、注册路由与全局异常处理器，并在 lifespan
      内初始化日志 / 数据库 / Redis，供 uvicorn 启动。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.configs.app_config import get_app_config
from app.configs.logging_config import setup_logging
from app.errors.handlers import register_exception_handlers
from app.models.base import init_db
from app.utils.redis_client import init_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期钩子
    作用：启动时初始化日志、数据库连接池与 Redis 客户端；关闭时释放 Redis 连接。
          初始化流程与 Celery Worker 的 ensure_worker_runtime() 保持一致。
    """
    config = get_app_config()

    # 初始化日志系统
    setup_logging(config.logging)
    logger.info("日志系统初始化完成")

    # 初始化数据库连接池（同步引擎 + SessionLocal）
    init_db(
        config.database.url,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        pool_pre_ping=config.database.pool_pre_ping,
        echo=config.database.echo,
    )
    logger.info("数据库连接池初始化完成")

    # 初始化 Redis 客户端（同步 + 异步，使用缓存库）
    init_redis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.cache_db,
        password=config.redis.password,
    )
    logger.info("Redis 客户端初始化完成")

    logger.info(f"应用启动完成: env={config.env} app={config.app.name}")

    yield

    # 关闭异步 Redis 连接
    from app.utils.redis_client import async_redis_client

    if async_redis_client is not None:
        await async_redis_client.close()
    logger.info("应用关闭，资源已释放")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用
    Return:
        - app: 已注册 CORS / 异常处理器 / 路由的 FastAPI 实例
    """
    app = FastAPI(
        title="入院量表评估 - AI 对话服务",
        description="住院患者入院评估的任务创建、AI 对话交互与 SSE 流式推送接口",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 配置 CORS：患者与医护使用独立 HttpOnly Cookie，开发期允许本地前端携带凭据
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://192.168.144.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册全局异常处理器
    register_exception_handlers(app)

    # 注册业务路由
    from app.api import (
        auth,
        consent,
        dialog,
        extraction,
        patients,
        patient_portal,
        quality,
        scales,
        sse,
        system_config,
        tasks,
        voice_dialog,
    )

    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(dialog.router)
    app.include_router(sse.router)
    app.include_router(patients.router)
    app.include_router(patient_portal.router)
    app.include_router(scales.router)
    app.include_router(system_config.router)
    app.include_router(extraction.router)
    app.include_router(quality.router)
    app.include_router(consent.router)
    app.include_router(voice_dialog.router)

    # 健康检查
    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """健康检查
        Return:
            - {status: ok}
        """
        return {"status": "ok"}

    return app


app = create_app()
