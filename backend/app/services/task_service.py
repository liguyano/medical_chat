"""评估任务服务
作用：封装 care_task 的创建与查询逻辑，做患者/住院记录存在性校验与任务编号生成。
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.schemas.task import CreateTaskRequest, TaskResponse

logger = logging.getLogger(__name__)


def _gen_task_no() -> str:
    """生成任务编号
    Return:
        - task_no: 形如 TASK-xxxxxxxx 的唯一编号
    """
    return f"TASK-{uuid.uuid4().hex[:12]}"


def _to_response(task: CareTask) -> TaskResponse:
    """将 ORM 任务转为响应模型
    Args:
        - task: CareTask ORM 实例
    Return:
        - TaskResponse
    """
    return TaskResponse(
        task_no=task.task_no,
        patient_id=task.patient_id,
        encounter_id=task.encounter_id,
        task_type=task.task_type,
        task_name=task.task_name,
        task_source=task.task_source,
        collection_mode=task.collection_mode,
        task_status=task.task_status,
        assigned_nurse_id=task.assigned_nurse_id,
        created_at=task.create_time,
    )


def create_task(db: Session, req: CreateTaskRequest) -> TaskResponse:
    """创建评估任务
    作用：校验患者与住院记录存在后落库 care_task，初始状态为 pending。
    Args:
        - db: 数据库会话
        - req: 创建任务请求
    Return:
        - TaskResponse: 新建任务详情
    """
    # 校验患者存在
    patient = db.execute(
        select(Patient).where(Patient.id == req.patient_id, Patient.deleted == 0)
    ).scalar_one_or_none()
    if patient is None:
        raise AppError(ErrorCode.ERR_TASK_001)

    # 校验住院记录存在且归属该患者
    encounter = db.execute(
        select(PatientEncounter).where(
            PatientEncounter.id == req.encounter_id,
            PatientEncounter.deleted == 0,
        )
    ).scalar_one_or_none()
    if encounter is None or encounter.patient_id != req.patient_id:
        raise AppError(ErrorCode.ERR_TASK_002)

    # 落库新任务
    task = CareTask(
        task_no=_gen_task_no(),
        patient_id=req.patient_id,
        encounter_id=req.encounter_id,
        task_type=req.task_type,
        task_name=req.task_name,
        task_source=req.task_source,
        collection_mode=req.collection_mode,
        task_status="pending",
        assigned_nurse_id=req.assigned_nurse_id,
        planned_start_time=req.planned_start_time,
        creator="system",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    logger.info(f"评估任务创建成功: task_no={task.task_no} patient_id={req.patient_id}")
    return _to_response(task)


def get_task(db: Session, task_no: str) -> TaskResponse:
    """按任务编号查询任务详情
    Args:
        - db: 数据库会话
        - task_no: 任务编号
    Return:
        - TaskResponse: 任务详情
    """
    task = db.execute(
        select(CareTask).where(CareTask.task_no == task_no, CareTask.deleted == 0)
    ).scalar_one_or_none()
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    return _to_response(task)
