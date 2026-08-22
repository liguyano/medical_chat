"""患者门户 API。

作用：提供患者鉴权后的通知、指南、住院助手和知情同意真实数据接口，
并提供医护端创建一次性扫码令牌。所有返回统一使用 ``{code,message,data}``。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_patient, require_staff, require_staff_or_patient
from app.configs.app_config import get_app_config
from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.base import get_db
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.schemas.patient_portal import (
    ConsentClauseConfirmRequest,
    ConsentPlaybackRequest,
    ConsentSnapshotDto,
    PatientAssistantMessageRequest,
    PatientAssistantSessionCreateRequest,
    PatientAssistantSessionDto,
    PatientNotificationDto,
    PatientScanTokenCreateRequest,
    PatientScanVerifyRequest,
    PatientTaskVerifyRequest,
    WardGuideDto,
)
from app.schemas.response import ApiResponse, ok
from app.services import patient_portal_service, patient_service

router = APIRouter(tags=["patient-portal"])
DbSession = Annotated[Session, Depends(get_db)]
PatientContext = Annotated[tuple[Patient, PatientEncounter], Depends(require_patient)]


def _set_patient_cookie(response: Response, token: str) -> None:
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


@router.post(
    "/api/patients/verify-task",
    response_model=ApiResponse[dict],
    summary="按任务编号和证件后四位登录患者端",
)
def verify_task(
    request: Request,
    response: Response,
    req: PatientTaskVerifyRequest,
    db: DbSession,
) -> dict:
    """核验当前在院任务并复用患者 HttpOnly Cookie。"""
    patient, encounter, task, token = patient_portal_service.verify_task_identity(
        db,
        request,
        task_no=req.task_no,
        id_card_suffix=req.id_card_suffix,
    )
    _set_patient_cookie(response, token)
    portal = patient_service.get_patient_portal(
        db,
        _request_with_cookie(request, get_app_config().security.patient_session_cookie, token),
    )
    return ok(
        {
            "patient": portal.patient.model_dump(mode="json"),
            "encounter": portal.encounter.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in portal.tasks],
            "verified_task_no": task.task_no,
            "verification_method": "task_no_id_card_suffix",
            "inpatient": encounter.encounter_status == "在院",
            "patient_name": patient.patient_name,
        }
    )


def _request_with_cookie(request: Request, cookie_name: str, token: str) -> Request:
    """为会话创建结果复用构造带 Cookie 的轻量 Request。"""
    scope = dict(request.scope)
    headers = list(scope.get("headers", []))
    headers = [(key, value) for key, value in headers if key.lower() != b"cookie"]
    headers.append((b"cookie", f"{cookie_name}={token}".encode()))
    scope["headers"] = headers
    return Request(scope, request.receive)


@router.post(
    "/api/patients/scan/token",
    response_model=ApiResponse[dict],
    summary="医护端创建一次性患者扫码令牌",
)
def create_scan_token(
    req: PatientScanTokenCreateRequest,
    db: DbSession,
    _: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """令牌只在 Redis 存储摘要，不能通过令牌枚举患者资料。"""
    return ok(
        patient_portal_service.create_scan_token(
            db,
            task_no=req.task_no,
            expires_in_seconds=req.expires_in_seconds,
        )
    )


@router.post(
    "/api/patients/scan/verify",
    response_model=ApiResponse[dict],
    summary="患者端消费一次性扫码令牌",
)
def verify_scan(
    request: Request,
    req: PatientScanVerifyRequest,
    response: Response,
    db: DbSession,
) -> dict:
    """消费成功后只返回当前患者门户数据并设置 HttpOnly Cookie。"""
    patient, encounter, task, token = patient_portal_service.consume_scan_token(
        db, req.token
    )
    _set_patient_cookie(response, token)
    portal = patient_service.get_patient_portal(
        db,
        _request_with_cookie(
            request, get_app_config().security.patient_session_cookie, token
        ),
    )
    return ok(
        {
            "patient": portal.patient.model_dump(mode="json"),
            "encounter": portal.encounter.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in portal.tasks],
            "patient_name": patient.patient_name,
            "task_no": task.task_no,
            "encounter_no": encounter.encounter_no,
            "verification_method": "scan_token",
        }
    )


@router.get(
    "/api/patient-notifications",
    response_model=ApiResponse[dict],
    summary="患者通知列表和未读数",
)
def list_patient_notifications(
    db: DbSession,
    context: PatientContext,
    unread_only: bool = False,
) -> dict:
    patient, encounter = context
    items, unread = patient_portal_service.list_notifications(
        db,
        patient_id=patient.id,
        encounter_id=encounter.id,
        unread_only=unread_only,
    )
    return ok({"items": [item.model_dump(mode="json") for item in items], "unread_count": unread})


@router.post(
    "/api/patient-notifications/{notification_id}/read",
    response_model=ApiResponse[PatientNotificationDto],
    summary="标记患者通知已读",
)
def mark_patient_notification_read(
    notification_id: int,
    db: DbSession,
    context: PatientContext,
) -> dict:
    patient, encounter = context
    return ok(
        patient_portal_service.mark_notification_read(
            db,
            patient_id=patient.id,
            encounter_id=encounter.id,
            notification_id=notification_id,
        ).model_dump(mode="json")
    )


@router.get(
    "/api/patient-ward-guide",
    response_model=ApiResponse[list[WardGuideDto]],
    summary="当前病区指南",
)
def get_patient_ward_guide(
    db: DbSession,
    context: PatientContext,
) -> dict:
    _, encounter = context
    return ok(
        patient_portal_service.list_ward_guides(
            db,
            department_code=encounter.department_code,
            department_name=encounter.department_name,
            ward_name=encounter.ward_name,
        )
    )


@router.post(
    "/api/patient-assistant/sessions",
    response_model=ApiResponse[PatientAssistantSessionDto],
    summary="创建住院助手会话",
)
def create_patient_assistant_session(
    req: PatientAssistantSessionCreateRequest,
    db: DbSession,
    context: PatientContext,
) -> dict:
    patient, encounter = context
    return ok(
        patient_portal_service.create_assistant_session(
            db,
            patient_id=patient.id,
            encounter_id=encounter.id,
            channel_type=req.channel_type,
        )
    )


@router.get(
    "/api/patient-assistant/sessions/{session_no}",
    response_model=ApiResponse[PatientAssistantSessionDto],
    summary="读取住院助手会话",
)
def get_patient_assistant_session(
    session_no: str,
    db: DbSession,
    context: PatientContext,
) -> dict:
    patient, encounter = context
    return ok(
        patient_portal_service.get_assistant_session(
            db,
            patient_id=patient.id,
            encounter_id=encounter.id,
            session_no=session_no,
        )
    )


@router.post(
    "/api/patient-assistant/sessions/{session_no}/messages",
    response_model=ApiResponse[PatientAssistantSessionDto],
    summary="发送住院生活问题",
)
def send_patient_assistant_message(
    session_no: str,
    req: PatientAssistantMessageRequest,
    db: DbSession,
    context: PatientContext,
) -> dict:
    patient, encounter = context
    return ok(
        patient_portal_service.send_assistant_message(
            db,
            patient_id=patient.id,
            encounter_id=encounter.id,
            session_no=session_no,
            content=req.content,
            client_message_id=req.client_message_id,
        )
    )


@router.get(
    "/api/consent-forms/{task_ref}/snapshot",
    response_model=ApiResponse[ConsentSnapshotDto],
    summary="获取任务知情同意文档快照",
)
def get_consent_form_snapshot(
    task_ref: str,
    db: DbSession,
    actor: Annotated[
        StaffAccount | tuple[Patient, PatientEncounter],
        Depends(require_staff_or_patient),
    ],
) -> dict:
    patient, encounter = _consent_actor_context(db, actor, task_ref)
    return ok(
        patient_portal_service.get_consent_snapshot(
            db,
            task_ref=task_ref,
            patient_id=patient.id,
            encounter_id=encounter.id,
        )
    )


@router.post(
    "/api/consent-forms/{task_ref}/playback",
    response_model=ApiResponse[dict],
    summary="记录知情同意条款播放进度",
)
def record_consent_playback(
    task_ref: str,
    req: ConsentPlaybackRequest,
    db: DbSession,
    context: PatientContext,
) -> dict:
    patient, encounter = context
    return ok(
        patient_portal_service.record_consent_playback(
            db,
            task_ref=task_ref,
            patient_id=patient.id,
            encounter_id=encounter.id,
            request=req,
        )
    )


@router.post(
    "/api/consent-forms/{task_ref}/clauses/{clause_id}/confirm",
    response_model=ApiResponse[dict],
    summary="确认知情同意条款",
)
def confirm_consent_clause(
    task_ref: str,
    clause_id: int,
    req: ConsentClauseConfirmRequest,
    db: DbSession,
    context: PatientContext,
) -> dict:
    patient, encounter = context
    return ok(
        patient_portal_service.confirm_consent_clause(
            db,
            task_ref=task_ref,
            patient_id=patient.id,
            encounter_id=encounter.id,
            clause_id=clause_id,
            request=req,
        )
    )


def _consent_actor_context(
    db: Session,
    actor: StaffAccount | tuple[Patient, PatientEncounter],
    task_ref: str,
) -> tuple[Patient, PatientEncounter]:
    """患者本人按 Cookie 访问；医护按任务查看签署结果。"""
    if isinstance(actor, tuple):
        return actor
    task = db.scalar(
        select(CareTask).where(
            CareTask.task_no == task_ref,
            CareTask.deleted == 0,
        )
    )
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    patient = db.get(Patient, task.patient_id)
    encounter = db.get(PatientEncounter, task.encounter_id)
    if patient is None or encounter is None:
        raise AppError(ErrorCode.ERR_PATIENT_005)
    return patient, encounter
