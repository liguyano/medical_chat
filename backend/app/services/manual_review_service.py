"""固定人工审核策略与通知服务。

固定人工审核由后端 question_code 白名单决定，AI 不参与是否触发的判断。
这些题从患者 AI 问答队列中排除，但在患者进度中从一开始视为已处理；
当 AI 可询问题全部完成后，系统幂等通知责任护士进行人工审核。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, TypeVar

from sqlalchemy import select

from app.models import base as model_base
from app.models.assessment_execution import AssessmentInstance
from app.models.assessment_template import AssessmentQuestion
from app.models.interaction import InteractionEvent, InteractionSession
from app.models.patient_task import CareTask, Patient, PatientEncounter
from app.schemas.events import HandoffRequestedEvent
from app.workers.event_publisher import DialogEventPublisher, NurseEventPublisher


FIXED_MANUAL_REVIEW_QUESTION_CODES = frozenset(
    {
        "outdoor_night_lighting",
        "indoor_stair_handrails",
    }
)

PLANNED_MANUAL_REVIEW_SOURCE_PREFIX = "system:planned-manual-review:"

T = TypeVar("T")


@dataclass(frozen=True)
class ManualReviewProgressSnapshot:
    """固定人工审核参与后的患者 AI 采集进度快照。"""

    current: int
    total: int
    completed: bool
    ai_required_question_ids: tuple[int, ...]
    manual_review_question_ids: tuple[int, ...]
    manual_review_pending_question_ids: tuple[int, ...]
    remaining_question_ids: tuple[int, ...]


@dataclass(frozen=True)
class ManualReviewItem:
    question_id: int
    question_code: str
    question_text: str


@dataclass(frozen=True)
class PlannedManualReviewNotification:
    """固定人工审核通知结果。"""

    item_count: int
    items: tuple[ManualReviewItem, ...]
    notified: bool
    request_id: str | None = None


def is_fixed_manual_review_question(question_code: str | None) -> bool:
    return str(question_code or "") in FIXED_MANUAL_REVIEW_QUESTION_CODES


def filter_ai_question_tasks(tasks: Iterable[T]) -> list[T]:
    """从 Schedule/Extraction/Qwen 可见题目中移除固定人工审核题。"""
    return [
        task
        for task in tasks
        if not is_fixed_manual_review_question(
            getattr(task, "question_code", None)
        )
    ]


def build_manual_review_progress(
    *,
    required_questions: Iterable[tuple[int, str]],
    answered_question_ids: Iterable[int],
) -> ManualReviewProgressSnapshot:
    """纯函数计算患者 AI 采集进度。

    固定人工审核题从一开始计入 current，但永远不进入 AI remaining；
    是否已经由护士写入真实答案只影响 manual_review_pending_question_ids。
    """
    ordered = list(
        dict.fromkeys((int(qid), str(code)) for qid, code in required_questions)
    )
    answered = {int(question_id) for question_id in answered_question_ids}
    manual_ids = tuple(
        question_id
        for question_id, code in ordered
        if is_fixed_manual_review_question(code)
    )
    manual_set = set(manual_ids)
    ai_required_ids = tuple(
        question_id for question_id, _ in ordered if question_id not in manual_set
    )
    remaining = tuple(
        question_id for question_id in ai_required_ids if question_id not in answered
    )
    pending_manual = tuple(
        question_id for question_id in manual_ids if question_id not in answered
    )
    ai_answered_count = sum(
        1 for question_id in ai_required_ids if question_id in answered
    )
    return ManualReviewProgressSnapshot(
        current=ai_answered_count + len(manual_ids),
        total=len(ordered),
        completed=bool(ordered) and not remaining,
        ai_required_question_ids=ai_required_ids,
        manual_review_question_ids=manual_ids,
        manual_review_pending_question_ids=pending_manual,
        remaining_question_ids=remaining,
    )


def load_manual_review_items(db: Any, task_id: int) -> tuple[ManualReviewItem, ...]:
    """加载当前任务绑定量表中的固定人工审核题。"""
    rows = db.execute(
        select(AssessmentQuestion)
        .join(
            AssessmentInstance,
            AssessmentInstance.scale_version_id == AssessmentQuestion.scale_version_id,
        )
        .where(
            AssessmentInstance.task_id == task_id,
            AssessmentInstance.deleted == 0,
            AssessmentQuestion.required.is_(True),
            AssessmentQuestion.derived.is_(False),
            AssessmentQuestion.deleted == 0,
            AssessmentQuestion.question_code.in_(FIXED_MANUAL_REVIEW_QUESTION_CODES),
        )
        .order_by(
            AssessmentQuestion.scale_version_id,
            AssessmentQuestion.sort_no,
            AssessmentQuestion.id,
        )
    ).scalars().all()
    return tuple(
        ManualReviewItem(
            question_id=question.id,
            question_code=question.question_code,
            question_text=question.question_name,
        )
        for question in rows
    )


def _source_invocation_id(task_id: int) -> str:
    return f"{PLANNED_MANUAL_REVIEW_SOURCE_PREFIX}{task_id}"


def ensure_planned_manual_review_notification(
    session_no: str,
) -> PlannedManualReviewNotification:
    """AI 采集完成后固定且幂等地通知责任护士。

    数据库只建立一条业务事件；重复调用会复用同一 request_id 并再次发布同一
    event_id，使“数据库已提交但流发布中断”的场景可以安全补发。前端按
    request_id/event_id 幂等消费。

    固定人工审核与患者主动呼叫医护是两个业务概念，因此这里不会设置
    InteractionSession.handoff_required/handoff_reason。
    """
    if model_base.SessionLocal is None:
        raise RuntimeError("数据库未初始化")

    publisher: DialogEventPublisher | None = None
    nurse_publisher: NurseEventPublisher | None = None
    event: HandoffRequestedEvent | None = None
    result: PlannedManualReviewNotification

    with model_base.SessionLocal() as db:
        session = db.scalar(
            select(InteractionSession).where(
                InteractionSession.session_no == session_no,
                InteractionSession.deleted == 0,
            )
        )
        if session is None:
            raise RuntimeError(f"交互会话不存在: {session_no}")
        task = db.get(CareTask, session.task_id)
        if task is None:
            raise RuntimeError(f"护理任务不存在: {session.task_id}")

        items = load_manual_review_items(db, task.id)
        if not items:
            return PlannedManualReviewNotification(
                item_count=0,
                items=(),
                notified=False,
            )

        source_id = _source_invocation_id(task.id)
        existing = db.scalar(
            select(InteractionEvent).where(
                InteractionEvent.interaction_session_id == session.id,
                InteractionEvent.source_invocation_id == source_id,
                InteractionEvent.deleted == 0,
            )
        )

        if existing is not None:
            payload = existing.event_payload or {}
            event = HandoffRequestedEvent.model_validate(payload)
            request_id = event.request_id
        else:
            patient = db.get(Patient, task.patient_id)
            encounter = db.get(PatientEncounter, task.encounter_id)
            request_id = f"MANUAL-REVIEW-{task.id}"
            item_payload = [
                {
                    "question_id": item.question_id,
                    "question_code": item.question_code,
                    "question_text": item.question_text,
                }
                for item in items
            ]
            description = "；".join(item.question_text for item in items)
            event = HandoffRequestedEvent(
                event_id=f"MANUAL-REVIEW-EVENT-{task.id}",
                session_id=session.session_no,
                task_id=task.id,
                message_id=None,
                request_id=request_id,
                reason=f"AI问答已完成，剩余{len(items)}项固定条目需要护士人工审核",
                requested_action="planned_manual_review",
                action_label=f"固定条目人工审核（{len(items)}项）",
                urgency="routine",
                priority="medium",
                title="固定条目待人工审核",
                description=description,
                patient_name=patient.patient_name if patient else "",
                bed_no=encounter.bed_no if encounter else None,
                ward_name=encounter.ward_name if encounter else None,
                status="requested",
                request_source="system",
                review_items=item_payload,
            )
            db.add(
                InteractionEvent(
                    interaction_session_id=session.id,
                    message_id=None,
                    event_type=event.event_type.value,
                    event_payload=event.model_dump(mode="json"),
                    handled_status="pending",
                    source_invocation_id=source_id,
                    creator="system:planned_manual_review",
                    updator="system:planned_manual_review",
                )
            )
            db.commit()

        publisher = DialogEventPublisher(session.session_no)
        if task.assigned_nurse_id is not None:
            nurse_publisher = NurseEventPublisher(
                task.assigned_nurse_id,
                publisher.redis,
            )
        result = PlannedManualReviewNotification(
            item_count=len(items),
            items=items,
            notified=True,
            request_id=request_id,
        )

    assert event is not None and publisher is not None
    publisher.publish(event)
    if nurse_publisher is not None:
        nurse_publisher.publish(event)
    return result
