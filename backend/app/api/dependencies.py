"""API 身份依赖。
作用：为需要医护或患者会话的业务路由提供统一依赖注入入口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.base import get_db
from app.models.patient_task import Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.services import patient_service, staff_service

DbSession = Annotated[Session, Depends(get_db)]


def require_staff(
    request: Request,
    db: DbSession,
) -> StaffAccount:
    """要求当前请求具备有效医护会话。"""
    return staff_service.get_staff_context(db, request)


def require_patient(
    request: Request,
    db: DbSession,
) -> tuple[Patient, PatientEncounter]:
    """要求当前请求具备有效患者会话。"""
    return patient_service.get_patient_context(db, request)


def require_staff_or_patient(
    request: Request,
    db: DbSession,
) -> StaffAccount | tuple[Patient, PatientEncounter]:
    """允许医护或患者会话访问共享只读接口。

    两类会话使用不同 Cookie；优先读取医护会话，便于护士端在同一浏览器中
    监控患者对话。
    """
    staff_cookie = request.cookies.get(
        get_app_config().security.staff_session_cookie
    )
    if staff_cookie:
        try:
            return staff_service.get_staff_context(db, request)
        except AppError as exc:
            if exc.code != ErrorCode.ERR_STAFF_002:
                raise
    return patient_service.get_patient_context(db, request)
