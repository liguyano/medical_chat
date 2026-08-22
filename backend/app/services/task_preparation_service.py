"""AI任务首问准备状态服务。

作用：持久化 Schedule prepare、Dialog preheat、Dialog opening 三阶段状态，
保证医护端可以查看准备进度，且患者端只在首问落库后看到任务。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import base as model_base
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask

PREPARATION_STAGES = (
    "schedule_prepare",
    "dialog_preheat",
    "dialog_opening",
)
PREPARATION_STATUS_NOT_REQUIRED = "not_required"
PREPARATION_STATUS_QUEUED = "queued"
PREPARATION_STATUS_RUNNING = "running"
PREPARATION_STATUS_READY = "ready"
PREPARATION_STATUS_FAILED = "failed"


def empty_preparation_detail() -> dict[str, Any]:
    """构造三个阶段的初始快照。"""
    return {
        "stages": {
            stage: {
                "status": "pending",
                "output": {},
                "error": None,
                "updated_at": None,
            }
            for stage in PREPARATION_STAGES
        }
    }


def initialize_ai_preparation(task: CareTask) -> None:
    """初始化 AI 对话任务的准备状态。"""
    task.preparation_status = PREPARATION_STATUS_QUEUED
    task.preparation_stage = PREPARATION_STAGES[0]
    task.preparation_error = None
    task.preparation_attempt = 0
    task.preparation_detail = empty_preparation_detail()
    task.patient_visible_at = None


def initialize_traditional_preparation(task: CareTask, now: datetime) -> None:
    """初始化传统问卷任务，传统任务无需后台首问准备。"""
    task.preparation_status = PREPARATION_STATUS_NOT_REQUIRED
    task.preparation_stage = None
    task.preparation_error = None
    task.preparation_attempt = 0
    task.preparation_detail = None
    task.patient_visible_at = now


def _load_task(db: Session, session_no: str) -> CareTask | None:
    """按会话业务编号加载任务。"""
    return db.scalar(
        select(CareTask)
        .join(InteractionSession, InteractionSession.task_id == CareTask.id)
        .where(
            InteractionSession.session_no == session_no,
            InteractionSession.deleted == 0,
            CareTask.deleted == 0,
        )
    )


def _stage_snapshot(task: CareTask, stage: str) -> dict[str, Any]:
    """读取或创建单阶段快照。"""
    detail = deepcopy(task.preparation_detail or empty_preparation_detail())
    stages = detail.setdefault("stages", {})
    snapshot = stages.setdefault(
        stage,
        {
            "status": "pending",
            "output": {},
            "error": None,
            "updated_at": None,
        },
    )
    task.preparation_detail = detail
    return snapshot


def _now_iso() -> str:
    """返回统一 UTC 时间文本。"""
    return datetime.now(UTC).isoformat()


def _persist(db: Session, task: CareTask) -> None:
    """更新任务审计字段并提交。"""
    task.updator = "opening_pipeline"
    db.commit()


def _with_session(callback) -> Any:
    """在 Celery 进程内使用独立数据库会话执行状态更新。"""
    if model_base.SessionLocal is None:
        return None
    with model_base.SessionLocal() as db:
        return callback(db)


def get_preparation_status(session_no: str) -> str | None:
    """读取准备总状态；数据库未初始化时返回 None。"""

    def read(db: Session) -> str | None:
        task = _load_task(db, session_no)
        return task.preparation_status if task is not None else None

    return _with_session(read)


def mark_stage_running(session_no: str, stage: str) -> bool:
    """记录某准备阶段开始执行。"""
    if stage not in PREPARATION_STAGES:
        raise ValueError(f"未知首问准备阶段: {stage}")

    def update(db: Session) -> bool:
        task = _load_task(db, session_no)
        if task is None or task.preparation_status == PREPARATION_STATUS_FAILED:
            return False
        snapshot = _stage_snapshot(task, stage)
        snapshot.update(
            {
                "status": "running",
                "error": None,
                "updated_at": _now_iso(),
            }
        )
        task.preparation_status = PREPARATION_STATUS_RUNNING
        task.preparation_stage = stage
        task.preparation_error = None
        _persist(db, task)
        return True

    return bool(_with_session(update))


def mark_stage_completed(
    session_no: str,
    stage: str,
    *,
    output: dict[str, Any] | None = None,
) -> bool:
    """记录某阶段成功，并推进下一阶段或发布患者可见性。"""
    if stage not in PREPARATION_STAGES:
        raise ValueError(f"未知首问准备阶段: {stage}")

    def update(db: Session) -> bool:
        task = _load_task(db, session_no)
        if task is None or task.preparation_status == PREPARATION_STATUS_FAILED:
            return False
        snapshot = _stage_snapshot(task, stage)
        snapshot.update(
            {
                "status": "completed",
                "output": output or {},
                "error": None,
                "updated_at": _now_iso(),
            }
        )
        index = PREPARATION_STAGES.index(stage)
        if index == len(PREPARATION_STAGES) - 1:
            task.preparation_status = PREPARATION_STATUS_READY
            task.preparation_stage = None
            task.preparation_error = None
            task.patient_visible_at = datetime.now(UTC)
        else:
            task.preparation_status = PREPARATION_STATUS_RUNNING
            task.preparation_stage = PREPARATION_STAGES[index + 1]
        _persist(db, task)
        return True

    return bool(_with_session(update))


def mark_stage_failure(
    session_no: str,
    stage: str,
    *,
    reason: str,
    retrying: bool,
) -> bool:
    """记录阶段错误；只有重试耗尽时才将任务置为最终失败。"""
    if stage not in PREPARATION_STAGES:
        raise ValueError(f"未知首问准备阶段: {stage}")

    def update(db: Session) -> bool:
        task = _load_task(db, session_no)
        if task is None:
            return False
        snapshot = _stage_snapshot(task, stage)
        snapshot.update(
            {
                "status": "running" if retrying else "failed",
                "error": reason,
                "updated_at": _now_iso(),
            }
        )
        task.preparation_stage = stage
        task.preparation_error = reason
        if not retrying:
            task.preparation_status = PREPARATION_STATUS_FAILED
            task.patient_visible_at = None
        else:
            task.preparation_status = PREPARATION_STATUS_RUNNING
        _persist(db, task)
        return True

    return bool(_with_session(update))


def reset_for_retry(db: Session, task: CareTask) -> None:
    """将失败的 AI 任务恢复为可重试的准备状态。"""
    next_attempt = int(task.preparation_attempt or 0) + 1
    initialize_ai_preparation(task)
    task.preparation_attempt = next_attempt
    task.updator = "staff:preparation_retry"


def preparation_payload(task: CareTask) -> dict[str, Any] | None:
    """将 ORM 字段转换成任务 DTO 使用的准备状态载荷。"""
    if task.collection_mode != "ai_dialogue":
        return None
    detail = deepcopy(task.preparation_detail or empty_preparation_detail())
    return {
        "status": task.preparation_status,
        "stage": task.preparation_stage,
        "attempt": int(task.preparation_attempt or 0),
        "error": task.preparation_error,
        "patient_visible_at": (
            task.patient_visible_at.isoformat()
            if task.patient_visible_at is not None
            else None
        ),
        "stages": detail.get("stages", {}),
    }
