"""共享题目状态服务：按真实患者交互恢复候选、当前题和冷却。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.models.assessment_execution import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentInstance,
    AssessmentSubmission,
)
from app.models.assessment_template import AssessmentQuestion, AssessmentScale
from app.models.interaction import InteractionEvent, InteractionMessage, InteractionSession
from app.models.patient_task import CareTask
from app.services.assessment_progress_service import valid_assessment_answer_condition


def _session(db, session_no, patient_id=None, staff_id=None, *, lock=False):
    """检查会话归属；写入时锁定会话以串行化幂等事件。"""
    query = select(InteractionSession).where(
        InteractionSession.session_no == session_no, InteractionSession.deleted == 0
    )
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        raise AppError(ErrorCode.ERR_DIALOG_001)
    task = db.get(CareTask, session.task_id)
    if (
        task is None
        or task.deleted
        or (patient_id is not None and patient_id != session.patient_id)
        or (staff_id is not None and staff_id != task.assigned_nurse_id)
    ):
        raise AppError(ErrorCode.ERR_DIALOG_004, "无权访问该会话")
    return session


def _history(db, session_id):
    """从消息顺序和已落库事件恢复患者轮编号，允许语音转写晚到。"""
    messages = db.scalars(
        select(InteractionMessage)
        .where(
            InteractionMessage.interaction_session_id == session_id, InteractionMessage.deleted == 0
        )
        .order_by(InteractionMessage.occurred_at, InteractionMessage.id)
    ).all()
    events = db.scalars(
        select(InteractionEvent)
        .where(
            InteractionEvent.interaction_session_id == session_id,
            InteractionEvent.event_type == "question_turn",
            InteractionEvent.deleted == 0,
        )
        .order_by(InteractionEvent.id)
    ).all()
    by_message = {event.message_id: event.event_payload for event in events}
    source_turns = {
        p["source_message_no"]: p["turn_number"]
        for p in by_message.values()
        if p.get("source_message_no")
    }
    turn = 0
    entries = []
    for message in messages:
        payload = by_message.get(message.id)
        if message.role_type in ("患者", "家属", "user"):
            if message.message_no not in source_turns:
                source_turns[message.message_no] = turn + 1
            turn = max(turn, source_turns[message.message_no])
        elif message.role_type in ("AI", "assistant"):
            if payload is not None:
                turn = max(turn, payload["turn_number"])
                entries.append(payload)
            elif message.related_question_id is not None or message.intent_type == "回应":
                entries.append(
                    {
                        "turn_number": turn,
                        "selected_question_id": None
                        if message.intent_type == "澄清"
                        else message.related_question_id,
                        "active_question_id": message.related_question_id,
                        "message_no": message.message_no,
                    }
                )
    return source_turns, entries, max([turn, *source_turns.values()])


def load_question_context(
    db: Session,
    session_no: str,
    source_message_no: str | None = None,
    patient_id: int | None = None,
    staff_id: int | None = None,
) -> dict:
    """读取任务绑定版本、有效答案与最多三道候选，不修改任何业务状态。"""
    session = _session(db, session_no, patient_id, staff_id)
    rows = db.execute(
        select(AssessmentQuestion, AssessmentScale.scale_name, AssessmentInstance.id)
        .join(
            AssessmentInstance,
            AssessmentInstance.scale_version_id == AssessmentQuestion.scale_version_id,
        )
        .join(AssessmentScale, AssessmentScale.id == AssessmentInstance.scale_id)
        .where(
            AssessmentInstance.task_id == session.task_id,
            AssessmentInstance.deleted == 0,
            AssessmentQuestion.deleted == 0,
            AssessmentQuestion.derived.is_(False),
        )
        .order_by(AssessmentInstance.id, AssessmentQuestion.sort_no, AssessmentQuestion.id)
    ).all()
    questions = {question.id: (question, scale_name) for question, scale_name, _ in rows}
    instance_ids = {instance_id for _, _, instance_id in rows}
    # 与结构化进度服务一致，每个实例仅取当前会话的最新提交。
    submissions = db.scalars(
        select(AssessmentSubmission)
        .where(
            AssessmentSubmission.assessment_instance_id.in_(instance_ids),
            AssessmentSubmission.interaction_session_id == session.id,
            AssessmentSubmission.deleted == 0,
        )
        .order_by(AssessmentSubmission.id)
    ).all()
    latest = {submission.assessment_instance_id: submission.id for submission in submissions}
    answers = db.scalars(
        select(AssessmentAnswer)
        .where(
            AssessmentAnswer.submission_id.in_(latest.values()),
            AssessmentAnswer.question_id.in_(questions),
            AssessmentAnswer.deleted == 0,
            valid_assessment_answer_condition(),
        )
        .order_by(AssessmentAnswer.id)
    ).all()
    recorded = {answer.question_id: answer for answer in answers}
    source_turns, entries, current_turn = _history(db, session.id)
    turn = (
        source_turns.get(source_message_no, current_turn + 1)
        if source_message_no is not None
        else current_turn
    )
    selected_at = {}
    active = None
    for entry in entries:
        # 指定来源时恢复生成前快照，重试不消费自身已生成的选择。
        if source_message_no is not None and entry["turn_number"] >= turn:
            continue
        selected = entry.get("selected_question_id")
        if selected in questions:
            selected_at[selected] = entry["turn_number"]
        active = entry.get("active_question_id")
    if active not in questions:
        active = None
    items = []
    for question_id, (question, scale_name) in questions.items():
        until = selected_at.get(question_id)
        until = until + 3 if until is not None else None
        items.append(
            {
                "question_id": question_id,
                "question_code": question.question_code,
                "question_text": question.patient_text or question.question_name,
                "scale_name": scale_name,
                "required": question.required,
                "status": "recorded"
                if question_id in recorded
                else "asked"
                if question_id in selected_at
                else "unasked",
                "is_current": question_id == active,
                "cooling_until_turn": until if until is not None and turn < until else None,
            }
        )
    eligible = [
        item
        for item in items
        if item["status"] != "recorded" and item["cooling_until_turn"] is None
    ]
    eligible.sort(key=lambda item: item["status"] != "unasked")
    labels = {}
    for option in db.scalars(
        select(AssessmentAnswerOption)
        .where(
            AssessmentAnswerOption.assessment_answer_id.in_([answer.id for answer in answers]),
            AssessmentAnswerOption.selected_flag.is_(True),
            AssessmentAnswerOption.deleted == 0,
        )
        .order_by(AssessmentAnswerOption.id)
    ).all():
        labels.setdefault(option.assessment_answer_id, []).append(option.option_label_snapshot)
    summaries = []
    for question_id, answer in recorded.items():
        value = "、".join(labels.get(answer.id, []))
        if not value:
            if answer.answer_boolean is not None:
                value = "是" if answer.answer_boolean else "否"
            else:
                value = next(
                    (
                        str(getattr(answer, field))
                        for field in (
                            "answer_text",
                            "answer_number",
                            "answer_date",
                            "answer_time",
                            "answer_datetime",
                        )
                        if getattr(answer, field) is not None
                    ),
                    "",
                )
        question = questions[question_id][0]
        summaries.append(
            {
                "question_id": question_id,
                "question_code": question.question_code,
                "question_text": question.patient_text or question.question_name,
                "display_value": value,
            }
        )
    return {
        "session_id": session_no,
        "current": sum(item["required"] and item["status"] == "recorded" for item in items),
        "total": sum(bool(item["required"]) for item in items),
        "turn_number": turn,
        "active_question_id": active,
        "candidate_question_ids": [item["question_id"] for item in eligible[:3]],
        "questions": items,
        "recorded_answers": summaries,
    }


def validate_decision(context: dict, payload: dict) -> dict:
    """验证显式选题；普通回复允许空值，澄清只关联此前当前题。"""
    if (
        not isinstance(payload, dict)
        or not {"selected_question_id", "active_question_id"} <= payload.keys()
    ):
        raise ValueError("必须明确报告选题与当前题")
    selected, active = payload["selected_question_id"], payload["active_question_id"]
    if any(
        value is not None and (type(value) is not int or value <= 0) for value in (selected, active)
    ):
        raise ValueError("题目编号必须为整数或 null")
    if selected is not None:
        if selected not in context["candidate_question_ids"] or active != selected:
            raise ValueError("新选题必须来自候选且与当前题一致")
    elif active is not None and active != context.get("active_question_id"):
        raise ValueError("澄清只能关联此前当前题")
    return {"selected_question_id": selected, "active_question_id": active}


def record_question_turn(
    db: Session,
    session_no: str,
    message_no: str,
    source_message_no: str | None,
    selected_question_id: int | None,
    active_question_id: int | None,
) -> dict:
    """完整 AI 消息落库后保存幂等选择事件，并同步消息题目关联。"""
    session = _session(db, session_no, lock=True)
    invocation = f"question_turn:{source_message_no or 'initial'}"
    existing = db.scalar(
        select(InteractionEvent).where(
            InteractionEvent.interaction_session_id == session.id,
            InteractionEvent.source_invocation_id == invocation,
            InteractionEvent.deleted == 0,
        )
    )
    if existing is not None:
        return dict(existing.event_payload)
    message = db.scalar(
        select(InteractionMessage).where(
            InteractionMessage.interaction_session_id == session.id,
            InteractionMessage.message_no == message_no,
            InteractionMessage.role_type.in_(["AI", "assistant"]),
            InteractionMessage.deleted == 0,
        )
    )
    if message is None:
        raise ValueError("必须先保存完整 AI 消息")
    context = load_question_context(db, session_no, source_message_no)
    # 选择在输出前按候选快照验证；输出期间抽取可改变答案，落库只复核归属和结构。
    question_ids = [item["question_id"] for item in context["questions"]]
    _, entries, _ = _history(db, session.id)
    previous = [
        entry
        for entry in entries
        if entry.get("message_no") != message_no and entry["turn_number"] <= context["turn_number"]
    ]
    previous_active = previous[-1].get("active_question_id") if previous else None
    decision = validate_decision(
        {"candidate_question_ids": question_ids, "active_question_id": previous_active},
        {"selected_question_id": selected_question_id, "active_question_id": active_question_id},
    )
    payload = {
        **decision,
        "source_message_no": source_message_no,
        "message_no": message_no,
        "turn_number": context["turn_number"],
    }
    message.related_question_id = active_question_id
    db.add(
        InteractionEvent(
            interaction_session_id=session.id,
            message_id=message.id,
            event_type="question_turn",
            event_payload=payload,
            source_invocation_id=invocation,
            handled_status="系统已处理",
            handled_by="dialog_agent",
            handled_at=datetime.now(UTC),
            creator="dialog_agent",
            updator="dialog_agent",
        )
    )
    db.commit()
    return payload
