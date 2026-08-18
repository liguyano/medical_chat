"""医护账号服务。
作用：封装医护账号登录、Redis 会话管理和当前医护身份读取。
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.staff_account import StaffAccount
from app.schemas.staff import StaffDto, StaffLoginRequest, StaffLoginResponse
from app.utils.password import verify_password
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)
SESSION_KEY_PREFIX = "staff_auth:"


def _session_key(token: str) -> str:
    """生成医护会话 Redis Key。"""
    return f"{SESSION_KEY_PREFIX}{token}"


def to_staff_dto(staff: StaffAccount) -> StaffDto:
    """转换医护账号公开 DTO，不返回密码哈希。"""
    return StaffDto(
        id=staff.id,
        staff_no=staff.staff_no,
        staff_name=staff.staff_name,
        role_code=staff.role_code,
        department_name=staff.department_name,
    )


def login_staff(
    db: Session,
    request: StaffLoginRequest,
) -> tuple[StaffLoginResponse, str]:
    """校验医护账号并创建 HttpOnly 会话。"""
    staff_no = request.staff_no.strip().upper()
    staff = db.scalar(
        select(StaffAccount).where(
            StaffAccount.staff_no == staff_no,
            StaffAccount.deleted == 0,
        )
    )
    if staff is None or not verify_password(request.password, staff.password_hash):
        raise AppError(ErrorCode.ERR_STAFF_001)
    if staff.account_status != "启用":
        raise AppError(ErrorCode.ERR_STAFF_003)

    token = secrets.token_urlsafe(32)
    config = get_app_config()
    session_saved = get_redis().set(
        _session_key(token),
        {
            "staff_id": staff.id,
            "staff_no": staff.staff_no,
        },
        ex=config.security.staff_session_ttl_seconds,
    )
    if not session_saved:
        raise AppError(ErrorCode.ERR_STAFF_004)

    return StaffLoginResponse(staff=to_staff_dto(staff)), token


def get_staff_context(db: Session, request: Request) -> StaffAccount:
    """读取当前医护登录会话并校验账号状态。"""
    cookie_name = get_app_config().security.staff_session_cookie
    token = request.cookies.get(cookie_name)
    if not token:
        raise AppError(ErrorCode.ERR_STAFF_002)

    payload = get_redis().get(_session_key(token))
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.ERR_STAFF_002)

    staff = db.scalar(
        select(StaffAccount).where(
            StaffAccount.id == payload.get("staff_id"),
            StaffAccount.deleted == 0,
            StaffAccount.account_status == "启用",
        )
    )
    if staff is None:
        raise AppError(ErrorCode.ERR_STAFF_002)
    return staff


def logout_staff(request: Request) -> None:
    """删除当前医护登录会话。"""
    cookie_name = get_app_config().security.staff_session_cookie
    token = request.cookies.get(cookie_name)
    if token:
        get_redis().delete(_session_key(token))
