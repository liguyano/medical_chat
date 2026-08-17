"""统一响应包装
作用：定义 API 层统一返回结构 {code, message, data}，供路由与异常处理器共用。
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.errors.codes import ErrorCode, default_message

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应体
    作用：所有接口以 {code, message, data} 结构返回，前端按 code 判定成败。
    类参数：
        - T: data 字段的业务数据类型
    """

    code: str = Field(default=ErrorCode.OK.value, description="业务错误码，成功为 OK")
    message: str = Field(default="成功", description="人类可读提示")
    data: T | None = Field(default=None, description="业务数据载荷")


def ok(data: Any = None, message: str = "成功") -> dict[str, Any]:
    """构造成功响应
    Args:
        - data: 业务数据
        - message: 提示文案
    Return:
        - 统一响应字典 {code: OK, message, data}
    """
    return {"code": ErrorCode.OK.value, "message": message, "data": data}


def fail(code: ErrorCode, message: str | None = None, data: Any = None) -> dict[str, Any]:
    """构造失败响应
    Args:
        - code: 业务错误码
        - message: 自定义提示，缺省时取错误码默认中文提示
        - data: 附加数据（可选）
    Return:
        - 统一响应字典 {code, message, data}
    """
    return {
        "code": code.value,
        "message": message or default_message(code),
        "data": data,
    }
