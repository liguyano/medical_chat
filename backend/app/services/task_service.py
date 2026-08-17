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
from app.schemas.task import BackendTaskDto, CreateTaskRequest, CreateTaskResponse

logger = logging.getLogger(__name__)


def _gen_task_no() -> str:
    """生成任务编号
    Return:
        - task_no: 形如 TASK-xxxxxxxx 的唯一编号
    """
    return f"TASK-{uuid.uuid4().hex[:12]}"


def _to_backend_task_dto(task: CareTask, session_no: str | None = None) -> BackendTaskDto:
    """将 ORM 任务转为后端任务 DTO
    Args:
        - task: CareTask ORM 实例
        - session_no: 会话编号（可选）
    Return:
        - BackendTaskDto
    """
    return BackendTaskDto(
        id=task.id,
        task_id=task.id,
        task_no=task.task_no,
        session_id=session_no,
        patient_id=task.patient_id,
        encounter_id=task.encounter_id,
        encounter_no=None,  # 第一期不填充关联字段
        patient_name=None,
        bed_no=None,
        department=None,
        ward_name=None,
        task_type=task.task_type,
        collection_mode=task.collection_mode,
        task_status=task.task_status,
        nurse_id=task.assigned_nurse_id,
        assigned_nurse_id=task.assigned_nurse_id,
        assigned_nurse_name=None,
        scale_ids=None,  # 第一期从 task_config JSONB 读取或留空
        scale_names=None,
        scale_version=None,
        participant_type=task.participant_type,
        participant_name=task.participant_name,
        relationship_to_patient=task.relationship_to_patient,
        assessment_scene=task.assessment_scene,
        consent_required=task.consent_required,
        education_topics=task.education_topics or [],
        planned_start_time=task.planned_start_time.isoformat() if task.planned_start_time else None,
        notes=task.notes,
        handoff_required=False,
        handoff_reason=None,
        current_stage=None,
        ai_summary=None,
        answered_question_count=None,
        total_question_count=None,
        created_at=task.create_time.isoformat() if task.create_time else "",
        updated_at=task.update_time.isoformat() if task.update_time else None,
        completed_at=None,
    )


def create_task(db: Session, req: CreateTaskRequest) -> CreateTaskResponse:
    """创建评估任务
    作用：校验患者与住院记录存在后落库 care_task，AI 对话模式预建 interaction_session。
    Args:
        - db: 数据库会话
        - req: 创建任务请求
    Return:
        - CreateTaskResponse: 新建任务响应
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

    # 落库新任务（扩展字段）
    task = CareTask(
        task_no=_gen_task_no(),
        patient_id=req.patient_id,
        encounter_id=req.encounter_id,
        task_type=req.task_type,
        task_name=req.task_name,
        task_source=req.task_source,
        collection_mode=req.collection_mode,
        task_status="pending",
        assigned_nurse_id=req.nurse_id,
        planned_start_time=req.planned_start_time,
        participant_type=req.participant_type,
        participant_name=req.participant_name,
        relationship_to_patient=req.relationship_to_patient,
        assessment_scene=req.assessment_scene,
        consent_required=req.consent_required,
        education_topics=req.education_topics,
        notes=req.notes,
        creator="system",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # AI 对话模式预建 interaction_session（第一期简化实现，返回 session_id）
    session_no = None
    if req.collection_mode == "ai_dialog":
        session_no = _create_interaction_session(db, task, req.scale_ids)

    logger.info(f"评估任务创建成功: task_no={task.task_no} session_no={session_no}")
    return CreateTaskResponse(
        task_id=task.id,
        task_no=task.task_no,
        session_id=session_no,
        status=task.task_status,
        task=_to_backend_task_dto(task, session_no),
    )


def _create_interaction_session(db: Session, task: CareTask, scale_ids: list[int]) -> str:
    """预建交互会话（AI 对话模式）
    作用：为 ai_dialog 任务创建 interaction_session 并派发四个后台 worker。
    Args:
        - db: 数据库会话
        - task: 关联任务
        - scale_ids: 量表ID列表
    Return:
        - session_no: 会话编号
    """
    from datetime import UTC, datetime
    from app.models.interaction import InteractionSession

    session_no = f"SESS-{uuid.uuid4().hex[:12]}"
    session = InteractionSession(
        session_no=session_no,
        task_id=task.id,
        patient_id=task.patient_id,
        encounter_id=task.encounter_id,
        participant_type=task.participant_type or "patient",
        interaction_type="assessment",
        channel_type="text",
        session_status="active",
        started_at=datetime.now(UTC),
        creator="system",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 派发四个后台 worker
    _dispatch_ai_dialog_workers(task, session_no, scale_ids)
    logger.info(f"预建交互会话并派发worker: session_no={session_no} task_no={task.task_no}")

    return session_no


def _dispatch_ai_dialog_workers(task: CareTask, session_no: str, scale_ids: list[int]) -> None:
    """派发 AI 对话四个后台 worker
    作用：派发 preheat + dialog_agent_worker + schedule_agent_worker + extraction_agent_worker
    Args:
        - task: 关联任务
        - session_no: 会话编号
        - scale_ids: 量表 ID 列表
    """
    from app.celery_app.tasks import (
        dialog_agent_preheat,
        dialog_agent_worker,
        extraction_agent_worker,
        schedule_agent_worker,
    )
    from app.models.assessment_template import AssessmentScale
    from app.models.base import SessionLocal

    # 查询 scale_codes（从 scale_ids）
    with SessionLocal() as db:
        scales = db.execute(
            select(AssessmentScale.scale_code).where(AssessmentScale.id.in_(scale_ids))
        ).scalars().all()
        scale_codes = list(scales)

    if not scale_codes:
        logger.warning(f"未找到量表编码: scale_ids={scale_ids}")
        return

    # 构造患者信息（简化版，从 task 获取）
    patient_info = {
        "patient_id": task.patient_id,
        "encounter_id": task.encounter_id,
        "participant_type": task.participant_type or "patient",
    }

    # 公共配置
    task_config = {
        "scale_codes": scale_codes,
        "check_interval": 5,
    }

    # 1. Dialog Agent Preheat（预热，初始化状态）
    dialog_agent_preheat.delay(session_no, patient_info, task_config)
    logger.info(f"派发 dialog_agent_preheat: session={session_no}")

    # 2. Dialog Agent Worker（主导问诊循环）
    dialog_agent_worker.delay(session_no, patient_info, task_config)
    logger.info(f"派发 dialog_agent_worker: session={session_no}")

    # 3. Schedule Agent Worker（约束检查与追加）
    schedule_agent_worker.delay(session_no, task_config)
    logger.info(f"派发 schedule_agent_worker: session={session_no}")

    # 4. Extraction Agent Worker（字段抽取与写库）
    extraction_agent_worker.delay(session_no, task_config)
    logger.info(f"派发 extraction_agent_worker: session={session_no}")


def get_task(db: Session, task_no: str) -> BackendTaskDto:
    """按任务编号查询任务详情
    Args:
        - db: 数据库会话
        - task_no: 任务编号
    Return:
        - BackendTaskDto: 任务详情
    """
    task = db.execute(
        select(CareTask).where(CareTask.task_no == task_no, CareTask.deleted == 0)
    ).scalar_one_or_none()
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)

    # 查询关联 session_no（如果存在）
    session_no = None
    if task.collection_mode == "ai_dialog":
        from app.models.interaction import InteractionSession

        session = db.execute(
            select(InteractionSession.session_no).where(
                InteractionSession.task_id == task.id,
                InteractionSession.deleted == 0,
            )
        ).scalar_one_or_none()
        session_no = session

    return _to_backend_task_dto(task, session_no)
