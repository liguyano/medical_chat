"""共享题目候选与交互轮记录的隔离数据库测试。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.models import (
    AssessmentAnswer,
    AssessmentInstance,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentSubmission,
    CareTask,
    InteractionEvent,
    InteractionMessage,
    InteractionSession,
)
from app.models.base import Base


@pytest.fixture
def db():
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(metadata)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if isinstance(column.type, BigInteger):
                column.type = Integer()
            if not column.primary_key:
                column.nullable = True
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                CareTask(id=1, assigned_nurse_id=8),
                InteractionSession(id=1, session_no="s", task_id=1, patient_id=7),
                AssessmentScale(id=1, scale_name="量表"),
                AssessmentInstance(id=1, task_id=1, scale_id=1, scale_version_id=1),
                AssessmentSubmission(id=1, assessment_instance_id=1, interaction_session_id=1),
                *[
                    AssessmentQuestion(
                        id=i,
                        scale_version_id=1,
                        question_code=f"q{i}",
                        question_name=f"题{i}",
                        patient_text=f"问{i}",
                        required=i != 5,
                        derived=False,
                        sort_no=i,
                    )
                    for i in range(1, 6)
                ],
            ]
        )
        session.commit()
        yield session
    engine.dispose()


def message(db, number, role="AI", related=None):
    item = InteractionMessage(
        interaction_session_id=1,
        message_no=number,
        role_type=role,
        turn_no=0,
        occurred_at=datetime.now(UTC),
        related_question_id=related,
    )
    db.add(item)
    db.commit()
    return item


def service():
    from app.services import dialog_question_service

    return dialog_question_service


def test_candidates_required_progress_and_valid_answers(db):
    db.add_all(
        [
            AssessmentAnswer(submission_id=1, question_id=1, answer_boolean=False),
            AssessmentAnswer(submission_id=1, question_id=2, answer_text="待人工确认"),
            AssessmentAnswer(
                submission_id=1, question_id=3, answer_text="有", extraction_confidence=0.2
            ),
        ]
    )
    db.commit()
    context = service().load_question_context(db, "s")
    assert context["candidate_question_ids"] == [2, 3, 4]
    assert (context["current"], context["total"]) == (1, 4)
    assert context["questions"][0]["status"] == "recorded"
    assert context["recorded_answers"][0]["display_value"] == "否"


def test_legacy_role_aliases_and_plain_reply_recover_without_guessing(db):
    svc = service()
    opening = message(db, "legacy-ai", "assistant", related=1)
    opening.intent_type = "提问"
    db.commit()
    message(db, "legacy-user", "user")
    context = svc.load_question_context(db, "s", "legacy-user")
    assert context["active_question_id"] == 1
    assert context["turn_number"] == 1
    reply = message(db, "plain-reply", "AI")
    reply.intent_type = "回应"
    db.commit()
    assert svc.load_question_context(db, "s")["active_question_id"] is None


def test_cooldown_two_patient_turns_and_clarification(db):
    svc = service()
    message(db, "a0")
    svc.record_question_turn(db, "s", "a0", None, 1, 1)
    for turn in (1, 2, 3):
        message(db, f"p{turn}", "患者")
        context = svc.load_question_context(db, "s", f"p{turn}")
        assert context["turn_number"] == turn
        assert (1 in context["candidate_question_ids"]) is False  # 未问题优先
        assert context["questions"][0]["cooling_until_turn"] == (3 if turn < 3 else None)
        if turn == 1:
            with pytest.raises(ValueError):
                svc.validate_decision(context, {"selected_question_id": 1, "active_question_id": 1})
            assert (
                svc.validate_decision(
                    context, {"selected_question_id": None, "active_question_id": 1}
                )["active_question_id"]
                == 1
            )
            message(db, "clarify")
            svc.record_question_turn(db, "s", "clarify", "p1", None, 1)
    for q in (2, 3, 4, 5):
        db.add(AssessmentAnswer(submission_id=1, question_id=q, answer_text="已答"))
    db.commit()
    assert svc.load_question_context(db, "s", "p3")["candidate_question_ids"] == [1]


def test_decision_rejects_invalid_and_accepts_null(db):
    context = service().load_question_context(db, "s")
    assert service().validate_decision(
        context, {"selected_question_id": None, "active_question_id": None}
    ) == {"selected_question_id": None, "active_question_id": None}
    for payload in (
        {},
        {"selected_question_id": 5, "active_question_id": 5},
        {"selected_question_id": None, "active_question_id": 1},
        {"selected_question_id": True, "active_question_id": True},
        {"selected_question_id": 1, "active_question_id": 2},
    ):
        with pytest.raises(ValueError):
            service().validate_decision(context, payload)


def test_pending_voice_source_is_idempotent_after_late_transcription(db):
    svc = service()
    assert svc.load_question_context(db, "s", "voice-p1")["turn_number"] == 1
    ai = message(db, "voice-a1")
    first = svc.record_question_turn(db, "s", ai.message_no, "voice-p1", 1, 1)
    assert svc.record_question_turn(db, "s", ai.message_no, "voice-p1", 1, 1) == first
    message(db, "voice-p1", "患者")
    assert svc.load_question_context(db, "s")["turn_number"] == 1
    assert len(db.scalars(select(InteractionEvent)).all()) == 1
    assert ai.related_question_id == 1
    assert svc.load_question_context(db, "s", "voice-p2")["turn_number"] == 2
    message(db, "voice-p2", "患者")
    assert svc.load_question_context(db, "s", "voice-p1")["turn_number"] == 1
    assert svc.load_question_context(db, "s", "voice-p1")["active_question_id"] is None


def test_history_fallback_and_access(db):
    message(db, "legacy", related=2)
    message(db, "ordinary")
    context = service().load_question_context(db, "s", patient_id=7)
    assert context["questions"][1]["status"] == "asked"
    assert context["questions"][0]["status"] == "unasked"
    from app.errors.handlers import AppError

    for actor in ({"patient_id": 9}, {"staff_id": 9}):
        with pytest.raises(AppError):
            service().load_question_context(db, "s", **actor)
    assert service().load_question_context(db, "s", staff_id=8)["session_id"] == "s"


def test_record_preserves_choice_when_answer_arrives_during_generation(db):
    svc = service()
    svc.validate_decision(
        svc.load_question_context(db, "s"), {"selected_question_id": 1, "active_question_id": 1}
    )
    db.add(AssessmentAnswer(submission_id=1, question_id=1, answer_text="已答"))
    db.commit()
    message(db, "a0", related=1)
    assert svc.record_question_turn(db, "s", "a0", None, 1, 1)["selected_question_id"] == 1


def test_progress_route_applies_staff_permission_and_hides_model_summaries(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.dependencies import require_staff_or_patient
    from app.api.dialog import router
    from app.models.base import get_db
    from app.models.staff_account import StaffAccount

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_staff_or_patient] = lambda: StaffAccount(id=8)
    with TestClient(app) as client:
        response = client.get("/api/dialog/s/question-progress")
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 4
    assert "recorded_answers" not in response.json()["data"]
