"""错误处理包
作用：暴露统一错误码与业务异常，供 API 层导入。
"""
from app.errors.codes import ErrorCode, default_http_status, default_message
from app.errors.handlers import AppError, register_exception_handlers

__all__ = [
    "ErrorCode",
    "default_http_status",
    "default_message",
    "AppError",
    "register_exception_handlers",
]
