"""评估任务路由
作用：提供任务创建与详情查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_patient, require_staff
from app.models.base import get_db
from app.models.patient_task import Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.schemas.interaction_tools import (
    EducationAcknowledgeRequest,
    HandoffRequest,
    HandoffResolveRequest,
)
from app.schemas.response import ApiResponse, ok
from app.schemas.task import BackendTaskDto, CreateTaskRequest, CreateTaskResponse
from app.services import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ApiResponse[CreateTaskResponse], summary="创建评估任务")
def create_task(
    req: CreateTaskRequest,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """创建评估任务
    Args:
        - req: 创建任务请求
        - db: 数据库会话
    Return:
        - CreateTaskResponse: 任务创建响应（裸载荷）
    """
    authenticated_request = req.model_copy(
        update={"assigned_nurse_id": staff.id},
    )
    return ok(task_service.create_task(db, authenticated_request))


@router.get(
    "/{task_ref}",
    response_model=ApiResponse[BackendTaskDto],
    summary="获取任务详情",
)
def get_task(
    task_ref: str,
    db: DbSession,
    _: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """获取任务详情
    Args:
        - task_ref: 任务主键或任务编号
        - db: 数据库会话
    Return:
        - BackendTaskDto: 任务详情（裸载荷）
    """
    return ok(task_service.get_task(db, task_ref))


@router.post(
    "/{task_ref}/handoff",
    response_model=ApiResponse[dict],
    summary="患者主动呼叫医护人员",
)
def request_handoff(
    task_ref: str,
    req: HandoffRequest,
    db: DbSession,
    patient_context: Annotated[
        tuple[Patient, PatientEncounter],
        Depends(require_patient),
    ],
) -> dict:
    """保存人工介入状态并推送责任护士全局提醒。"""
    from app.services import tool_interaction_service

    patient, _ = patient_context
    return ok(
        tool_interaction_service.request_handoff(
            db,
            task_ref,
            req,
            patient_id=patient.id,
        )
    )


@router.post(
    "/{task_ref}/handoff/resolve",
    response_model=ApiResponse[dict],
    summary="医护人员处理人工介入请求",
)
def resolve_handoff(
    task_ref: str,
    req: HandoffResolveRequest,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """解除人工介入状态，并向患者端发布处理完成事件。"""
    from app.services import tool_interaction_service

    return ok(
        tool_interaction_service.resolve_handoff(
            db,
            task_ref,
            req,
            staff_id=staff.id,
            staff_no=staff.staff_no,
            staff_name=staff.staff_name,
        )
    )


@router.post(
    "/{task_ref}/education/acknowledge",
    response_model=ApiResponse[dict],
    summary="患者确认已阅读医学宣教",
)
def acknowledge_education(
    task_ref: str,
    req: EducationAcknowledgeRequest,
    db: DbSession,
    patient_context: Annotated[
        tuple[Patient, PatientEncounter],
        Depends(require_patient),
    ],
) -> dict:
    """保存患者阅读宣教材料的结果，并向医护端推送状态事件。"""
    from app.services import tool_interaction_service

    patient, _ = patient_context
    return ok(
        tool_interaction_service.acknowledge_education(
            db,
            task_ref,
            req,
            patient_id=patient.id,
        )
    )
