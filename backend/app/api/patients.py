"""患者路由
作用：提供在院患者查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.configs.app_config import get_app_config
from app.models.base import get_db
from app.schemas.patient import (
    InHospitalPatientDto,
    PatientLoginRequest,
    PatientLoginResponse,
)
from app.schemas.response import ApiResponse, ok
from app.schemas.task import BackendTaskDto
from app.services import patient_service

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.get(
    "/in-hospital",
    response_model=ApiResponse[list[InHospitalPatientDto]],
    summary="查询在院患者列表",
)
def list_in_hospital_patients(
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """查询在院患者列表
    作用：返回 encounter_status="在院" 的患者及其住院记录。
    Args:
        - db: 数据库会话
    Return:
        - 在院患者列表（患者 + 住院记录）
    """
    return ok(patient_service.list_in_hospital_patients(db))


@router.post(
    "/login",
    response_model=ApiResponse[PatientLoginResponse],
    summary="患者身份登录",
)
def login_patient(
    req: PatientLoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """使用身份证号和手机号登录患者端。"""
    result, token = patient_service.login_patient(db, req)
    config = get_app_config()
    response.set_cookie(
        key=config.security.patient_session_cookie,
        value=token,
        max_age=config.security.patient_session_ttl_seconds,
        httponly=True,
        secure=config.security.patient_session_secure,
        samesite="lax",
        path="/",
    )
    return ok(result)


@router.get(
    "/me",
    response_model=ApiResponse[PatientLoginResponse],
    summary="获取当前患者信息和任务",
)
def get_current_patient(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """获取当前患者住院信息和本人任务。"""
    return ok(patient_service.get_patient_portal(db, request))


@router.get(
    "/me/tasks",
    response_model=ApiResponse[list[BackendTaskDto]],
    summary="获取当前患者任务",
)
def list_current_patient_tasks(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """获取当前患者当前住院记录下的护理任务。"""
    portal = patient_service.get_patient_portal(db, request)
    return ok(portal.tasks)


@router.post("/logout", summary="患者退出登录")
def logout_patient(request: Request, response: Response) -> dict:
    """退出患者端并清理会话 Cookie。"""
    patient_service.logout_patient(request)
    response.delete_cookie(
        key=get_app_config().security.patient_session_cookie,
        path="/",
    )
    return ok()
