"""人工题不冒充答案，不阻塞患者/AI 采集的 PostgreSQL 回归测试。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.errors.handlers import AppError
from app.managers.assessment_loader import AssessmentQuestionLoader
from app.models import (
    AssessmentAnswer,
    AssessmentInstance,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSubmission,
    InteractionSession,
    Patient,
    PatientEncounter,
)
from app.schemas.questionnaire import QuestionnaireAnswersRequest
from app.schemas.task import CreateTaskRequest
from app.services.assessment_progress_service import refresh_assessment_progress
from app.services.extraction_service import get_extracted_fields
from app.services.questionnaire_service import _build_dto, _save_answers
from app.services.task_service import _to_backend_task_dto, create_task


@pytest.fixture
def manual_case(postgres_session_factory, monkeypatch):
    """事务回滚隔离数据，只替换后台派发以避免真实队列/模型调用。"""
    from app.services import agent_dispatch_service

    monkeypatch.setattr(agent_dispatch_service, "dispatch_opening_workers", lambda *a: None)
    with postgres_session_factory() as db:
        suffix = uuid4().hex[:12]
        patient = Patient(patient_no=f"MP-{suffix}", patient_name="人工题测试")
        scale = AssessmentScale(
            scale_code=f"MS-{suffix}", scale_name="测试量表", scale_type="综合", status="已发布"
        )
        db.add_all([patient, scale])
        db.flush()
        encounter = PatientEncounter(
            encounter_no=f"ME-{suffix}",
            patient_id=patient.id,
            admission_time=datetime.now(UTC),
            encounter_status="在院",
        )
        version = AssessmentScaleVersion(
            scale_id=scale.id,
            version_code="v1",
            version_name="v1",
            publish_status="已发布",
            scale_snapshot={},
            content_hash=suffix,
        )
        db.add_all([encounter, version])
        db.flush()
        questions = []
        for index, manual in enumerate((False, True)):
            q = AssessmentQuestion(
                scale_version_id=version.id,
                question_code=f"Q{index}",
                question_name=f"问题{index}",
                original_text=f"问题{index}",
                patient_text=f"问题{index}",
                question_type="text",
                value_type="string",
                required=True,
                scored=False,
                derived=False,
                validation_rule={"manual_required": manual},
                sort_no=index,
            )
            db.add(q)
            questions.append(q)
        db.commit()
        yield db, patient, encounter, scale, version, questions


def _task(case, mode="ai_dialogue"):
    db, patient, encounter, scale, _, _ = case
    return create_task(
        db,
        CreateTaskRequest(
            patient_id=patient.id,
            encounter_id=encounter.id,
            scale_ids=[scale.id],
            collection_mode=mode,
        ),
    )


def test_ai_loader_and_progress_skip_manual_without_fake_answers(manual_case):
    db, _, _, scale, version, questions = manual_case
    result = _task(manual_case)
    loaded = AssessmentQuestionLoader._load_version_questions(db, scale.scale_code, version.id)
    assert [q.question_id for q in loaded] == [questions[0].id]
    progress = refresh_assessment_progress(db, result.session_id)
    assert (progress.current, progress.total, progress.remaining_question_ids) == (
        0,
        1,
        (questions[0].id,),
    )
    fields = get_extracted_fields(db, result.session_id).fields
    manual = next(f for f in fields if f.question_id == questions[1].id)
    assert manual.manual_required is True
    assert manual.answer_text is None and manual.display_value is None
    assert (
        db.scalar(
            select(func.count(AssessmentAnswer.id))
            .join(AssessmentQuestion)
            .where(AssessmentQuestion.scale_version_id == version.id)
        )
        == 0
    )
    from app.models.patient_task import CareTask

    task = db.get(CareTask, result.task_id)
    assert _to_backend_task_dto(db, task).total_question_count == 1
    assert not task.need_manual_intervention


def test_questionnaire_manual_is_readonly_and_not_required_for_submission(manual_case):
    db, _, _, _, _, _ = manual_case
    result = _task(manual_case, "traditional_form")
    from app.models.patient_task import CareTask

    task = db.get(CareTask, result.task_id)
    dto = _build_dto(db, task)
    assert dto.questions[1].manual_required is True
    submissions, missing = _save_answers(
        db,
        task,
        QuestionnaireAnswersRequest(task_id=str(task.id), answers={"Q0": "患者回答"}),
        actor="patient:test",
    )
    assert missing == []
    assert submissions[0][3].total_question_count == 1
    assert submissions[0][3].answered_question_count == 1
    with pytest.raises(AppError, match="人工"):
        _save_answers(
            db,
            task,
            QuestionnaireAnswersRequest(task_id=str(task.id), answers={"Q1": "伪造答案"}),
            actor="patient:test",
        )


def test_all_manual_ai_task_is_visible_waiting_review_without_agents(manual_case, monkeypatch):
    db, _, _, _, _, questions = manual_case
    for question in questions:
        question.validation_rule = {"manual_required": True}
    db.commit()
    from app.services import agent_dispatch_service

    def unexpected_dispatch(*args):
        pytest.fail("全人工题任务不应启动 AI 首问或呼叫护士")

    monkeypatch.setattr(agent_dispatch_service, "dispatch_opening_workers", unexpected_dispatch)
    result = _task(manual_case)
    assert result.status == "pending_review"
    assert result.task.preparation.patient_visible_at is not None
    fields = get_extracted_fields(db, result.session_id).fields
    assert len(fields) == 2 and all(f.manual_required for f in fields)


def test_manual_required_with_optional_automatic_starts_in_pending_review(
    manual_case, monkeypatch
):
    db, _, _, _, _, questions = manual_case
    questions[0].required = False
    db.commit()
    from app.services import agent_dispatch_service

    def unexpected_dispatch(*args):
        pytest.fail("没有自动必填题时不应启动 AI 首问")

    monkeypatch.setattr(agent_dispatch_service, "dispatch_opening_workers", unexpected_dispatch)
    result = _task(manual_case)
    progress = refresh_assessment_progress(db, result.session_id)
    assert result.status == "pending_review"
    assert (progress.current, progress.total, progress.completed) == (0, 0, True)


def test_json_flag_only_boolean_true_is_manual(manual_case):
    db, _, _, scale, version, questions = manual_case
    for value in (False, "true", None, 1):
        questions[1].validation_rule = {"manual_required": value}
        db.flush()
        loaded = AssessmentQuestionLoader._load_version_questions(db, scale.scale_code, version.id)
        assert len(loaded) == 2


def test_pending_manual_does_not_prevent_ai_completion(manual_case):
    db, _, _, _, _, questions = manual_case
    result = _task(manual_case)
    session = db.scalar(
        select(InteractionSession).where(InteractionSession.session_no == result.session_id)
    )
    instance = db.scalar(
        select(AssessmentInstance).where(AssessmentInstance.task_id == result.task_id)
    )
    submission = AssessmentSubmission(
        submission_no=f"SUB-{uuid4().hex}",
        assessment_instance_id=instance.id,
        submission_type="ai_extraction",
        submitter_type="ai",
        interaction_session_id=session.id,
        submission_status="in_progress",
    )
    db.add(submission)
    db.flush()
    db.add(
        AssessmentAnswer(
            submission_id=submission.id,
            question_id=questions[0].id,
            answer_type="text",
            answer_text="真实答案",
            value_source="ai_extracted",
        )
    )
    db.commit()
    progress = refresh_assessment_progress(db, result.session_id)
    assert (progress.current, progress.total, progress.completed) == (1, 1, True)
    assert progress.remaining_question_ids == ()


def test_cached_tasks_and_voice_database_fallback_skip_manual(
    manual_case, monkeypatch, postgres_session_factory
):
    from types import SimpleNamespace

    from app.models import base
    from app.services.manual_question_service import filter_manual_tasks
    from app.services.voice_turn_guard import VoiceTurnGuard

    db, _, _, _, _, questions = manual_case
    monkeypatch.setattr(base, "SessionLocal", postgres_session_factory)
    cached = [SimpleNamespace(question_id=q.id) for q in questions]
    assert [q.question_id for q in filter_manual_tasks(cached)] == [questions[0].id]
    assert VoiceTurnGuard._load_question_task_from_db(db, questions[1].id) is None


def test_all_manual_questionnaire_accepts_empty_patient_submission(manual_case):
    db, _, _, _, _, questions = manual_case
    for question in questions:
        question.validation_rule = {"manual_required": True}
    db.commit()
    result = _task(manual_case, "traditional_form")
    from app.models.patient_task import CareTask

    task = db.get(CareTask, result.task_id)
    submissions, missing = _save_answers(
        db,
        task,
        QuestionnaireAnswersRequest(task_id=str(task.id), answers={}),
        actor="patient:test",
    )
    assert missing == []
    assert submissions[0][3].total_question_count == 0
    assert submissions[0][3].answered_question_count == 0


def test_existing_nurse_answer_is_displayed_without_calling_nurse(manual_case):
    db, _, _, _, _, questions = manual_case
    result = _task(manual_case)
    session = db.scalar(
        select(InteractionSession).where(InteractionSession.session_no == result.session_id)
    )
    instance = db.scalar(
        select(AssessmentInstance).where(AssessmentInstance.task_id == result.task_id)
    )
    submission = AssessmentSubmission(
        submission_no=f"SUB-{uuid4().hex}",
        assessment_instance_id=instance.id,
        submission_type="ai_extraction",
        submitter_type="ai",
        interaction_session_id=session.id,
        submission_status="in_progress",
    )
    db.add(submission)
    db.flush()
    db.add(
        AssessmentAnswer(
            submission_id=submission.id,
            question_id=questions[1].id,
            answer_type="text",
            answer_text="护士测量结果",
            value_source="nurse_corrected",
        )
    )
    db.commit()
    fields = get_extracted_fields(db, result.session_id).fields
    manual = next(f for f in fields if f.question_id == questions[1].id)
    assert manual.manual_required and manual.display_value == "护士测量结果"
    assert not session.handoff_required


def test_manual_score_is_not_treated_as_zero(manual_case):
    from app.services.questionnaire_service import _save_score

    db, _, _, scale, version, questions = manual_case
    questions[1].scored = True
    db.commit()
    result = _task(manual_case, "traditional_form")
    from app.models.patient_task import CareTask

    task = db.get(CareTask, result.task_id)
    submissions, _ = _save_answers(
        db,
        task,
        QuestionnaireAnswersRequest(task_id=str(task.id), answers={"Q0": "正常"}),
        actor="patient:test",
    )
    instance, _, _, submission = submissions[0]
    score = _save_score(
        db,
        submission=submission,
        instance=instance,
        version=version,
        scale=scale,
        answer_ids=[],
        creator="pytest",
    )
    assert score.total_score is None and score.risk_level is None
    assert submission.total_score is None


@pytest.mark.asyncio
async def test_ai_score_waits_for_manual_scored_answer(
    manual_case, postgres_session_factory
):
    from app.managers.extraction_result_writer import ExtractionResultWriter

    db, _, _, _, version, questions = manual_case
    questions[1].scored = True
    db.commit()
    result = _task(manual_case)
    session = db.scalar(
        select(InteractionSession).where(InteractionSession.session_no == result.session_id)
    )
    instance = db.scalar(
        select(AssessmentInstance).where(AssessmentInstance.task_id == result.task_id)
    )
    submission = AssessmentSubmission(
        submission_no=f"SUB-{uuid4().hex}",
        assessment_instance_id=instance.id,
        submission_type="ai_extraction",
        submitter_type="ai",
        interaction_session_id=session.id,
        submission_status="in_progress",
        total_score=0,
        risk_level="low_risk",
    )
    db.add(submission)
    db.commit()
    scores = await ExtractionResultWriter(postgres_session_factory).calculate_scores(
        submission.id, version.id, creator="pytest"
    )
    db.expire(submission)
    assert scores == []
    assert submission.total_score is None and submission.risk_level is None


def test_config_manual_flag_roundtrips_without_losing_validation(manual_case):
    from app.schemas.system_config import AssessmentScaleConfigUpdateRequest
    from app.services.system_config_service import get_scale_config, update_scale_config

    db, _, _, scale, _, questions = manual_case
    detail = get_scale_config(db, scale.id)
    request = AssessmentScaleConfigUpdateRequest.model_validate(detail.model_dump())
    request.questions[0].validation_rule = {"manual_required": True, "min": 5}
    saved = update_scale_config(db, scale.id, request, operator="pytest")
    assert saved.questions[0].validation_rule == {"manual_required": True, "min": 5}
    db.expire(questions[0])
    assert questions[0].validation_rule == {"manual_required": True, "min": 5}


def test_nurse_cannot_finalize_pending_manual_question_as_completed(manual_case, monkeypatch):
    from app.schemas.assessment_review import AssessmentReviewRequest
    from app.services.assessment_review_service import submit_assessment_review

    db, _, _, _, _, _ = manual_case
    result = _task(manual_case, "traditional_form")
    from app.celery_app.tasks import nursing_plan_worker

    monkeypatch.setattr(nursing_plan_worker, "delay", lambda *a, **kw: None)
    with pytest.raises(AppError, match="人工"):
        submit_assessment_review(
            db,
            str(result.task_id),
            AssessmentReviewRequest(
                task_id=str(result.task_id),
                status="confirmed",
                nurse_answers={"Q0": "正常"},
                final_answers={"Q0": "正常", "Q1": "等待人工"},
            ),
            staff_id=1,
        )
