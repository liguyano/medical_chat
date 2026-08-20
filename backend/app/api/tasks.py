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
from app.schemas.assessment_review import AssessmentReviewRequest
from app.schemas.interaction_tools import (
    EducationAcknowledgeRequest,
    HandoffRequest,
    HandoffResolveRequest,
)
from app.schemas.nursing_plan import (
    NursingPlanDto,
    NursingPlanGenerateRequest,
    NursingPlanUpdateRequest,
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
    "",
    response_model=ApiResponse[list[BackendTaskDto]],
    summary="查询当前医护负责的全部任务",
)
def list_staff_tasks(
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """返回当前登录医护负责的历史与进行中任务。"""
    return ok(task_service.list_staff_tasks(db, staff_id=staff.id))


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


@router.get(
    "/{task_ref}/nursing-plan",
    response_model=ApiResponse[NursingPlanDto | None],
    summary="查询患者画像与护理计划",
)
def get_nursing_plan(
    task_ref: str,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """查询任务最近一次患者画像和护理计划。"""
    from app.services import nursing_plan_service

    return ok(
        nursing_plan_service.get_nursing_plan(
            db,
            task_ref,
            staff_id=staff.id,
        )
    )


@router.post(
    "/{task_ref}/review",
    response_model=ApiResponse[dict],
    summary="保存护士评估复核结果",
)
def submit_assessment_review(
    task_ref: str,
    req: AssessmentReviewRequest,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """保存护士独立结果、最终结果和差异原因。"""
    from app.services import assessment_review_service

    return ok(
        assessment_review_service.submit_assessment_review(
            db,
            task_ref,
            req,
            staff_id=staff.id,
        )
    )


@router.post(
    "/{task_ref}/nursing-plan/generate",
    response_model=ApiResponse[NursingPlanDto],
    summary="生成或重新生成护理计划草案",
)
async def generate_nursing_plan(
    task_ref: str,
    req: NursingPlanGenerateRequest,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """使用真实模型生成患者画像和护理计划 AI 草案。"""
    from app.services import nursing_plan_service

    return ok(
        await nursing_plan_service.generate_nursing_plan(
            db,
            task_ref,
            staff_id=staff.id,
            force=req.force,
        )
    )


@router.put(
    "/{task_ref}/nursing-plan",
    response_model=ApiResponse[NursingPlanDto],
    summary="编辑护理计划草案",
)
def update_nursing_plan(
    task_ref: str,
    req: NursingPlanUpdateRequest,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """保存护士对护理计划摘要和明细的编辑与处置。"""
    from app.services import nursing_plan_service

    return ok(
        nursing_plan_service.update_nursing_plan(
            db,
            task_ref,
            req,
            staff_id=staff.id,
            operator=staff.staff_no,
        )
    )


@router.post(
    "/{task_ref}/nursing-plan/confirm",
    response_model=ApiResponse[NursingPlanDto],
    summary="确认护理计划",
)
def confirm_nursing_plan(
    task_ref: str,
    db: DbSession,
    staff: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """由责任护士确认最终护理指导方案。"""
    from app.services import nursing_plan_service

    return ok(
        nursing_plan_service.confirm_nursing_plan(
            db,
            task_ref,
            staff_id=staff.id,
            operator=staff.staff_no,
        )
    )
