"""医护端身份认证路由。
作用：提供医护账号登录、当前用户查询和退出登录接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.models.base import get_db
from app.schemas.response import ApiResponse, ok
from app.schemas.staff import StaffLoginRequest, StaffLoginResponse
from app.services import staff_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/staff/login",
    response_model=ApiResponse[StaffLoginResponse],
    summary="医护账号登录",
)
def login_staff(
    req: StaffLoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """使用工号和密码登录医护端。"""
    result, token = staff_service.login_staff(db, req)
    config = get_app_config()
    response.set_cookie(
        key=config.security.staff_session_cookie,
        value=token,
        max_age=config.security.staff_session_ttl_seconds,
        httponly=True,
        secure=config.security.staff_session_secure,
        samesite="lax",
        path="/",
    )
    return ok(result)


@router.get(
    "/staff/me",
    response_model=ApiResponse[StaffLoginResponse],
    summary="获取当前医护账号",
)
def get_current_staff(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """返回当前有效医护会话的账号信息。"""
    staff = staff_service.get_staff_context(db, request)
    return ok(StaffLoginResponse(staff=staff_service.to_staff_dto(staff)))


@router.post("/staff/logout", summary="医护账号退出登录")
def logout_staff(request: Request, response: Response) -> dict:
    """退出医护端并清理会话 Cookie。"""
    staff_service.logout_staff(request)
    response.delete_cookie(
        key=get_app_config().security.staff_session_cookie,
        path="/",
    )
    return ok()
