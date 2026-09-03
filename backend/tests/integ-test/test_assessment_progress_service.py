"""结构化评估进度完成条件集成测试。"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.models import (
    AssessmentAnswer,
    AssessmentInstance,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSubmission,
    CareTask,
    InteractionSession,
    Patient,
    PatientEncounter,
)
from app.services.assessment_progress_service import (
    complete_assessment_session,
    refresh_assessment_progress,
)


def _no(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def test_only_required_structured_answers_can_complete_dialogue(
    postgres_session_factory,
):
    """患者消息轮数不能完成任务，两个必填结构化答案齐全后才完成。"""
    now = datetime.now(UTC)
    with postgres_session_factory() as db:
        patient = Patient(
            patient_no=_no("PAT"),
            patient_name="进度测试患者",
            creator="pytest",
            updator="pytest",
        )
        db.add(patient)
        db.flush()
        encounter = PatientEncounter(
            encounter_no=_no("ENC"),
            patient_id=patient.id,
            admission_time=now,
            encounter_status="在院",
            creator="pytest",
            updator="pytest",
        )
        db.add(encounter)
        db.flush()
        task = CareTask(
            task_no=_no("TASK"),
            patient_id=patient.id,
            encounter_id=encounter.id,
            task_type="入院评估",
            task_name="进度测试",
            task_source="护士创建",
            collection_mode="ai_dialogue",
            task_status="in_progress",
            creator="pytest",
            updator="pytest",
        )
        scale = AssessmentScale(
            scale_code=_no("SCALE"),
            scale_name="进度测试量表",
            scale_type="综合",
            status="已发布",
            creator="pytest",
            updator="pytest",
        )
        db.add_all([task, scale])
        db.flush()
        version = AssessmentScaleVersion(
            scale_id=scale.id,
            version_code="v1",
            version_name="v1",
            publish_status="已发布",
            scale_snapshot={},
            content_hash=uuid4().hex,
            creator="pytest",
            updator="pytest",
        )
        db.add(version)
        db.flush()
        questions = []
        for index, required in ((1, True), (2, True), (3, False)):
            question = AssessmentQuestion(
                scale_version_id=version.id,
                question_code=f"Q{index}",
                question_name=f"问题{index}",
                original_text=f"问题{index}",
                patient_text=f"问题{index}",
                question_type="文本",
                value_type="文本",
                required=required,
                scored=False,
                derived=False,
                sort_no=index,
                creator="pytest",
                updator="pytest",
            )
            db.add(question)
            questions.append(question)
        db.flush()
        session = InteractionSession(
            session_no=_no("SESS"),
            task_id=task.id,
            patient_id=patient.id,
            encounter_id=encounter.id,
            participant_type="patient",
            interaction_type="assessment",
            channel_type="text",
            session_status="active",
            started_at=now,
            creator="pytest",
            updator="pytest",
        )
        instance = AssessmentInstance(
            instance_no=_no("INST"),
            task_id=task.id,
            patient_id=patient.id,
            encounter_id=encounter.id,
            scale_id=scale.id,
            scale_version_id=version.id,
            assessment_scene="admission",
            instance_status="collecting",
            patient_name_snapshot=patient.patient_name,
            form_snapshot={},
            creator="pytest",
            updator="pytest",
        )
        db.add_all([session, instance])
        db.flush()
        submission = AssessmentSubmission(
            submission_no=_no("SUB"),
            assessment_instance_id=instance.id,
            submission_type="ai_extraction",
            submitter_type="ai",
            interaction_session_id=session.id,
            submission_status="in_progress",
            total_question_count=0,
            answered_question_count=0,
            creator="pytest",
            updator="pytest",
        )
        db.add(submission)
        db.commit()

        progress = refresh_assessment_progress(db, session.session_no)
        assert (progress.current, progress.total, progress.completed) == (0, 2, False)

        first_answer = AssessmentAnswer(
            submission_id=submission.id,
            question_id=questions[0].id,
            answer_type="文本",
            answer_text=None,
            extraction_confidence=Decimal("0.95"),
            value_source="ai_extracted",
            creator="pytest",
            updator="pytest",
        )
        db.add(first_answer)
        db.commit()
        progress = refresh_assessment_progress(db, session.session_no)
        assert (progress.current, progress.total, progress.completed) == (0, 2, False)

        first_answer.answer_text = "差不多"
        first_answer.extraction_confidence = Decimal("0.45")
        db.commit()
        progress = refresh_assessment_progress(db, session.session_no)
        assert (progress.current, progress.total, progress.completed) == (0, 2, False)

        first_answer.answer_text = "待人工确认"
        first_answer.extraction_confidence = Decimal("0.95")
        db.commit()
        progress = refresh_assessment_progress(db, session.session_no)
        assert (progress.current, progress.total, progress.completed) == (0, 2, False)

        first_answer.answer_text = "有效回答"
        first_answer.extraction_confidence = Decimal("0.95")
        db.commit()
        progress = complete_assessment_session(db, session.session_no)
        assert (progress.current, progress.total, progress.completed) == (1, 2, False)

        db.add(
            AssessmentAnswer(
                submission_id=submission.id,
                question_id=questions[1].id,
                answer_type="boolean",
                answer_boolean=False,
                extraction_confidence=Decimal("0.98"),
                value_source="ai_extracted",
                creator="pytest",
                updator="pytest",
            )
        )
        db.commit()
        progress = complete_assessment_session(db, session.session_no)

        assert (progress.current, progress.total, progress.completed) == (2, 2, True)
        db.refresh(session)
        db.refresh(task)
        assert session.session_status == "completed"
        assert task.task_status == "pending_review"
