"""统一错误码体系
作用：集中定义业务错误码，格式为 ERR_<域>_<三位序号>，供 API 层与异常处理器使用。
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """业务错误码枚举
    作用：以稳定字符串常量标识错误类型，前端可据此做差异化处理。
    命名：ERR_<域>_<NNN>，域包括 COMMON / TASK / DIALOG / SSE / KEYWORD。
    """

    # 通用域
    OK = "OK"  # 成功（非错误，占位）
    ERR_COMMON_001 = "ERR_COMMON_001"  # 请求参数校验失败
    ERR_COMMON_002 = "ERR_COMMON_002"  # 资源不存在
    ERR_COMMON_003 = "ERR_COMMON_003"  # 资源状态冲突
    ERR_COMMON_500 = "ERR_COMMON_500"  # 服务器内部错误

    # 任务域
    ERR_TASK_001 = "ERR_TASK_001"  # 患者不存在
    ERR_TASK_002 = "ERR_TASK_002"  # 住院记录不存在
    ERR_TASK_003 = "ERR_TASK_003"  # 任务不存在
    ERR_TASK_004 = "ERR_TASK_004"  # 量表不存在或不可用
    ERR_TASK_005 = "ERR_TASK_005"  # 后台任务派发失败

    # 患者身份域
    ERR_PATIENT_001 = "ERR_PATIENT_001"  # 身份信息不匹配
    ERR_PATIENT_002 = "ERR_PATIENT_002"  # 未办理入院
    ERR_PATIENT_003 = "ERR_PATIENT_003"  # 患者登录会话无效
    ERR_PATIENT_004 = "ERR_PATIENT_004"  # 患者登录会话保存失败

    # 对话域
    ERR_DIALOG_001 = "ERR_DIALOG_001"  # 会话不存在
    ERR_DIALOG_002 = "ERR_DIALOG_002"  # 会话状态不允许当前操作
    ERR_DIALOG_003 = "ERR_DIALOG_003"  # 并发冲突（未获取到会话锁）
    ERR_DIALOG_004 = "ERR_DIALOG_004"  # 关联任务不存在或不可对话

    # SSE 域
    ERR_SSE_001 = "ERR_SSE_001"  # 会话流不存在

    # 关键词域
    ERR_KEYWORD_001 = "ERR_KEYWORD_001"  # 规则加载失败


# 错误码 -> 默认中文提示
ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.OK: "成功",
    ErrorCode.ERR_COMMON_001: "请求参数校验失败",
    ErrorCode.ERR_COMMON_002: "资源不存在",
    ErrorCode.ERR_COMMON_003: "资源状态冲突",
    ErrorCode.ERR_COMMON_500: "服务器内部错误",
    ErrorCode.ERR_TASK_001: "患者不存在",
    ErrorCode.ERR_TASK_002: "住院记录不存在",
    ErrorCode.ERR_TASK_003: "评估任务不存在",
    ErrorCode.ERR_TASK_004: "量表不存在、未发布或已失效",
    ErrorCode.ERR_TASK_005: "后台任务派发失败",
    ErrorCode.ERR_PATIENT_001: "身份证号或手机号不匹配",
    ErrorCode.ERR_PATIENT_002: "您还未办理入院，暂不能进入患者端",
    ErrorCode.ERR_PATIENT_003: "患者登录已失效，请重新登录",
    ErrorCode.ERR_PATIENT_004: "患者登录服务暂不可用",
    ErrorCode.ERR_DIALOG_001: "交互会话不存在",
    ErrorCode.ERR_DIALOG_002: "会话当前状态不允许该操作",
    ErrorCode.ERR_DIALOG_003: "会话正在处理其他消息，请稍后重试",
    ErrorCode.ERR_DIALOG_004: "关联任务不存在或不可进行对话",
    ErrorCode.ERR_SSE_001: "会话事件流不存在",
    ErrorCode.ERR_KEYWORD_001: "关键词规则加载失败",
}


# 错误码 -> 建议 HTTP 状态码
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.ERR_COMMON_001: 422,
    ErrorCode.ERR_COMMON_002: 404,
    ErrorCode.ERR_COMMON_003: 409,
    ErrorCode.ERR_COMMON_500: 500,
    ErrorCode.ERR_TASK_001: 404,
    ErrorCode.ERR_TASK_002: 404,
    ErrorCode.ERR_TASK_003: 404,
    ErrorCode.ERR_TASK_004: 422,
    ErrorCode.ERR_TASK_005: 503,
    ErrorCode.ERR_PATIENT_001: 401,
    ErrorCode.ERR_PATIENT_002: 403,
    ErrorCode.ERR_PATIENT_003: 401,
    ErrorCode.ERR_PATIENT_004: 503,
    ErrorCode.ERR_DIALOG_001: 404,
    ErrorCode.ERR_DIALOG_002: 409,
    ErrorCode.ERR_DIALOG_003: 409,
    ErrorCode.ERR_DIALOG_004: 404,
    ErrorCode.ERR_SSE_001: 404,
    ErrorCode.ERR_KEYWORD_001: 500,
}


def default_message(code: ErrorCode) -> str:
    """获取错误码默认中文提示
    Args:
        - code: 错误码
    Return:
        - 中文提示，未登记时回退为错误码本身
    """
    return ERROR_MESSAGES.get(code, code.value)


def default_http_status(code: ErrorCode) -> int:
    """获取错误码建议 HTTP 状态码
    Args:
        - code: 错误码
    Return:
        - HTTP 状态码，未登记时回退为 400
    """
    return ERROR_HTTP_STATUS.get(code, 400)
