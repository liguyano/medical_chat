"""评估任务服务
作用：原子创建护理任务、交互会话和多量表评估实例，并派发第一期文本智能体。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentInstance,
    AssessmentSubmission,
)
from app.models.assessment_template import (
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
)
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.models.staff_account import StaffAccount
from app.schemas.task import BackendTaskDto, CreateTaskRequest, CreateTaskResponse

logger = logging.getLogger(__name__)


def _business_no(prefix: str, length: int = 12) -> str:
    """生成业务编号。"""
    return f"{prefix}-{uuid.uuid4().hex[:length].upper()}"


def _calculate_age(birthday: date | None, today: date | None = None) -> int | None:
    """计算周岁。"""
    if birthday is None:
        return None
    current = today or datetime.now(UTC).date()
    return (
        current.year
        - birthday.year
        - ((current.month, current.day) < (birthday.month, birthday.day))
    )


def _load_selected_versions(
    db: Session,
    scale_ids: list[int],
) -> list[tuple[AssessmentScale, AssessmentScaleVersion]]:
    """加载所选量表的当前已发布版本。"""
    now = datetime.now(UTC)
    rows = db.execute(
        select(AssessmentScale, AssessmentScaleVersion)
        .join(
            AssessmentScaleVersion,
            AssessmentScaleVersion.scale_id == AssessmentScale.id,
        )
        .where(
            AssessmentScale.id.in_(scale_ids),
            AssessmentScale.deleted == 0,
            AssessmentScaleVersion.deleted == 0,
            AssessmentScaleVersion.publish_status == "已发布",
            or_(
                AssessmentScaleVersion.effective_time.is_(None),
                AssessmentScaleVersion.effective_time <= now,
            ),
            or_(
                AssessmentScaleVersion.expire_time.is_(None),
                AssessmentScaleVersion.expire_time > now,
            ),
        )
        .order_by(
            AssessmentScale.id.asc(),
            AssessmentScaleVersion.effective_time.desc().nullslast(),
            AssessmentScaleVersion.id.desc(),
        )
    ).all()
    latest_by_scale: dict[int, tuple[AssessmentScale, AssessmentScaleVersion]] = {}
    for scale, version in rows:
        latest_by_scale.setdefault(scale.id, (scale, version))
    missing = [scale_id for scale_id in scale_ids if scale_id not in latest_by_scale]
    if missing:
        raise AppError(
            ErrorCode.ERR_TASK_004,
            f"量表不存在、未发布或已失效: {missing}",
        )
    return [latest_by_scale[scale_id] for scale_id in scale_ids]


def _build_instance(
    *,
    task: CareTask,
    patient: Patient,
    encounter: PatientEncounter,
    scale: AssessmentScale,
    version: AssessmentScaleVersion,
    assessment_scene: str,
    started_at: datetime,
) -> AssessmentInstance:
    """构造量表评估实例并保存业务快照。"""
    form_snapshot = dict(version.scale_snapshot or {})
    form_snapshot.update(
        {
            "scale_id": scale.id,
            "scale_code": scale.scale_code,
            "scale_name": scale.scale_name,
            "version_id": version.id,
            "version_code": version.version_code,
        }
    )
    return AssessmentInstance(
        instance_no=_business_no("INST", 16),
        task_id=task.id,
        patient_id=patient.id,
        encounter_id=encounter.id,
        scale_id=scale.id,
        scale_version_id=version.id,
        assessment_scene=assessment_scene,
        instance_status="collecting",
        started_at=started_at,
        assessor_type="ai",
        patient_name_snapshot=patient.patient_name,
        sex_snapshot=patient.sex,
        age_snapshot=_calculate_age(patient.birthday),
        department_name_snapshot=encounter.department_name,
        ward_name_snapshot=encounter.ward_name,
        bed_no_snapshot=encounter.bed_no,
        inpatient_no_snapshot=encounter.inpatient_no,
        diagnosis_snapshot=encounter.diagnosis_snapshot,
        form_snapshot=form_snapshot,
        creator="system",
        updator="system",
    )


def create_task(db: Session, req: CreateTaskRequest) -> CreateTaskResponse:
    """创建评估任务并启动AI文本问诊。"""
    patient = db.scalar(select(Patient).where(Patient.id == req.patient_id, Patient.deleted == 0))
    if patient is None:
        raise AppError(ErrorCode.ERR_TASK_001)

    encounter = db.scalar(
        select(PatientEncounter).where(
            PatientEncounter.id == req.encounter_id,
            PatientEncounter.deleted == 0,
        )
    )
    if encounter is None or encounter.patient_id != patient.id:
        raise AppError(ErrorCode.ERR_TASK_002)

    if req.assigned_nurse_id is not None:
        assigned_staff = db.scalar(
            select(StaffAccount.id).where(
                StaffAccount.id == req.assigned_nurse_id,
                StaffAccount.deleted == 0,
                StaffAccount.account_status == "启用",
            )
        )
        if assigned_staff is None:
            raise AppError(ErrorCode.ERR_STAFF_003)

    selected_versions = _load_selected_versions(db, req.scale_ids)
    now = datetime.now(UTC)
    task = CareTask(
        task_no=_business_no("TASK"),
        patient_id=patient.id,
        encounter_id=encounter.id,
        task_type=req.task_type,
        task_name=req.task_name,
        task_source=req.task_source,
        collection_mode=req.collection_mode,
        task_status="in_progress" if req.collection_mode == "ai_dialogue" else "pending",
        assigned_nurse_id=req.assigned_nurse_id,
        planned_start_time=req.planned_start_time,
        started_at=now if req.collection_mode == "ai_dialogue" else None,
        creator="system",
        updator="system",
    )
    session: InteractionSession | None = None
    try:
        db.add(task)
        db.flush()
        if req.collection_mode == "ai_dialogue":
            session = InteractionSession(
                session_no=_business_no("SESS"),
                task_id=task.id,
                patient_id=patient.id,
                encounter_id=encounter.id,
                participant_type=req.participant_type,
                interaction_type="assessment",
                channel_type="text",
                session_status="active",
                started_at=now,
                creator="system",
                updator="system",
            )
            db.add(session)

        for scale, version in selected_versions:
            db.add(
                _build_instance(
                    task=task,
                    patient=patient,
                    encounter=encounter,
                    scale=scale,
                    version=version,
                    assessment_scene=req.assessment_scene,
                    started_at=now,
                )
            )
        db.commit()
        db.refresh(task)
        if session is not None:
            db.refresh(session)
    except Exception:
        db.rollback()
        logger.exception("创建评估任务事务失败")
        raise

    if session is not None:
        from app.services.agent_dispatch_service import dispatch_opening_workers

        dispatch_opening_workers(db, session)

    dto = _to_backend_task_dto(db, task)
    return CreateTaskResponse(
        task_id=task.id,
        task_no=task.task_no,
        session_id=session.session_no if session else None,
        status=task.task_status,
        task=dto,
    )


def _to_backend_task_dto(db: Session, task: CareTask) -> BackendTaskDto:
    """将任务及关联数据转换为详情DTO。"""
    patient = db.get(Patient, task.patient_id)
    encounter = db.get(PatientEncounter, task.encounter_id)
    session = db.scalar(
        select(InteractionSession)
        .where(
            InteractionSession.task_id == task.id,
            InteractionSession.deleted == 0,
        )
        .order_by(InteractionSession.id.desc())
    )
    scale_rows = db.execute(
        select(AssessmentInstance, AssessmentScale, AssessmentScaleVersion)
        .join(AssessmentScale, AssessmentScale.id == AssessmentInstance.scale_id)
        .join(
            AssessmentScaleVersion,
            AssessmentScaleVersion.id == AssessmentInstance.scale_version_id,
        )
        .where(
            AssessmentInstance.task_id == task.id,
            AssessmentInstance.deleted == 0,
        )
        .order_by(AssessmentInstance.id.asc())
    ).all()
    version_ids = [version.id for _, _, version in scale_rows]
    total_questions = 0
    if version_ids:
        total_questions = int(
            db.scalar(
                select(func.count(AssessmentQuestion.id)).where(
                    AssessmentQuestion.scale_version_id.in_(version_ids),
                    AssessmentQuestion.derived.is_(False),
                    AssessmentQuestion.deleted == 0,
                )
            )
            or 0
        )
    answered_questions = 0
    if session is not None:
        answered_questions = int(
            db.scalar(
                select(func.count(func.distinct(AssessmentAnswer.question_id)))
                .join(
                    AssessmentSubmission,
                    AssessmentSubmission.id == AssessmentAnswer.submission_id,
                )
                .where(
                    AssessmentSubmission.interaction_session_id == session.id,
                    AssessmentSubmission.deleted == 0,
                    AssessmentAnswer.deleted == 0,
                )
            )
            or 0
        )

    versions = list(dict.fromkeys(version.version_code for _, _, version in scale_rows))
    return BackendTaskDto(
        id=task.id,
        task_id=task.id,
        task_no=task.task_no,
        session_id=session.session_no if session else None,
        patient_id=task.patient_id,
        encounter_id=task.encounter_id,
        encounter_no=encounter.encounter_no if encounter else "",
        patient_name=patient.patient_name if patient else "",
        bed_no=encounter.bed_no if encounter else None,
        department=encounter.department_name if encounter else None,
        ward_name=encounter.ward_name if encounter else None,
        task_type=task.task_type,
        collection_mode=task.collection_mode or "traditional_form",
        task_status=task.task_status,
        assigned_nurse_id=task.assigned_nurse_id,
        scale_ids=[scale.id for _, scale, _ in scale_rows],
        scale_names=[scale.scale_name for _, scale, _ in scale_rows],
        scale_version=",".join(versions) if versions else None,
        participant_type=session.participant_type if session else None,
        assessment_scene=scale_rows[0][0].assessment_scene if scale_rows else None,
        handoff_required=bool(session.handoff_required) if session else False,
        handoff_reason=session.handoff_reason if session else None,
        ai_summary=session.ai_summary if session else None,
        answered_question_count=answered_questions,
        total_question_count=total_questions,
        planned_start_time=(
            task.planned_start_time.isoformat() if task.planned_start_time else None
        ),
        created_at=task.create_time.isoformat(),
        updated_at=task.update_time.isoformat() if task.update_time else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


def get_task(db: Session, task_ref: str) -> BackendTaskDto:
    """按任务主键或业务编号查询详情。"""
    conditions = [CareTask.task_no == task_ref]
    if task_ref.isdigit():
        conditions.append(CareTask.id == int(task_ref))
    task = db.scalar(select(CareTask).where(or_(*conditions), CareTask.deleted == 0))
    if task is None:
        raise AppError(ErrorCode.ERR_TASK_003)
    return _to_backend_task_dto(db, task)


def list_patient_tasks(
    db: Session,
    *,
    patient_id: int,
    encounter_id: int,
) -> list[BackendTaskDto]:
    """查询患者当前住院记录下的护理任务。"""
    tasks = db.scalars(
        select(CareTask)
        .where(
            CareTask.patient_id == patient_id,
            CareTask.encounter_id == encounter_id,
            CareTask.deleted == 0,
        )
        .order_by(CareTask.create_time.desc(), CareTask.id.desc())
    ).all()
    return [_to_backend_task_dto(db, task) for task in tasks]
