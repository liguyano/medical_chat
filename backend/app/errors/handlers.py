"""全局异常处理
作用：定义业务异常 AppError 与 FastAPI 全局异常处理器，统一以 {code, message, data} 返回。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors.codes import ErrorCode, default_http_status, default_message
from app.schemas.response import fail

logger = logging.getLogger(__name__)


class AppError(Exception):
    """业务异常
    作用：业务逻辑主动抛出的可预期异常，携带错误码与提示，供处理器转为统一响应。
    类参数：
        - code: 业务错误码
        - message: 自定义提示，缺省时取错误码默认中文提示
        - http_status: 自定义 HTTP 状态码，缺省时取错误码建议状态码
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or default_message(code)
        self.http_status = http_status or default_http_status(code)
        super().__init__(self.message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器
    作用：将业务异常、请求校验异常、HTTP 异常与未捕获异常统一转为 {code, message, data}。
    Args:
        - app: FastAPI 应用实例
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        """处理业务异常"""
        logger.info(f"业务异常: {exc.code.value} - {exc.message}")
        return JSONResponse(
            status_code=exc.http_status,
            content=fail(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理请求参数校验异常"""
        detail = exc.errors()
        logger.info(f"参数校验失败: {detail}")
        return JSONResponse(
            status_code=default_http_status(ErrorCode.ERR_COMMON_001),
            content=fail(ErrorCode.ERR_COMMON_001, data=str(detail)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """处理 Starlette/FastAPI HTTP 异常（如 404 路由不存在）"""
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(ErrorCode.ERR_COMMON_002, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unknown_error(_: Request, exc: Exception) -> JSONResponse:
        """兜底处理未捕获异常"""
        logger.exception(f"服务器内部错误: {exc}")
        return JSONResponse(
            status_code=default_http_status(ErrorCode.ERR_COMMON_500),
            content=fail(ErrorCode.ERR_COMMON_500),
        )
