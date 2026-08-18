"""需求1批次 A 领域模型 PostgreSQL 集成测试。"""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import (
    AssessmentAnswer,
    AssessmentInstance,
    AssessmentOption,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSubmission,
    CareTask,
    InteractionMessage,
    InteractionMessageFeedback,
    InteractionSession,
    Patient,
    PatientEncounter,
    QualityReview,
    QualityReviewDimension,
    QualityReviewScore,
    QualityReviewTemplate,
)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _seed_domain_chain(session_factory) -> dict:
    """构建患者到评估问题、交互会话的最小完整链路。"""
    now = datetime.now(UTC)
    with session_factory() as db:
        patient = Patient(
            patient_no=_uid("PAT"),
            patient_name="测试患者",
            sex="未知",
            creator="pytest",
            updator="pytest",
        )
        db.add(patient)
        db.flush()

        encounter = PatientEncounter(
            encounter_no=_uid("ENC"),
            patient_id=patient.id,
            inpatient_no=_uid("INP"),
            admission_time=now,
            encounter_status="在院",
            creator="pytest",
            updator="pytest",
        )
        db.add(encounter)
        db.flush()

        task = CareTask(
            task_no=_uid("TASK"),
            patient_id=patient.id,
            encounter_id=encounter.id,
            task_type="入院评估",
            task_name="入院量表评估",
            task_source="护士创建",
            collection_mode="ai_dialogue",
            task_status="进行中",
            creator="pytest",
            updator="pytest",
        )
        scale = AssessmentScale(
            scale_code=_uid("SCALE"),
            scale_name="测试量表",
            scale_type="综合信息采集表",
            status="已发布",
            creator="pytest",
            updator="pytest",
        )
        db.add_all([task, scale])
        db.flush()

        scale_version = AssessmentScaleVersion(
            scale_id=scale.id,
            version_code="v1",
            version_name="第一版",
            publish_status="已发布",
            scale_snapshot={"name": "测试量表", "version": "v1"},
            content_hash=uuid4().hex,
            creator="pytest",
            updator="pytest",
        )
        db.add(scale_version)
        db.flush()

        question = AssessmentQuestion(
            scale_version_id=scale_version.id,
            question_code="Q001",
            question_name="年龄",
            original_text="年龄",
            patient_text="请问您今年多大年纪？",
            question_type="数字",
            value_type="整数",
            required=True,
            scored=False,
            creator="pytest",
            updator="pytest",
        )
        db.add(question)
        db.flush()

        option = AssessmentOption(
            question_id=question.id,
            option_code="UNKNOWN",
            option_label="不清楚",
            option_value="unknown",
            creator="pytest",
            updator="pytest",
        )
        interaction_session = InteractionSession(
            session_no=_uid("SESSION"),
            task_id=task.id,
            patient_id=patient.id,
            encounter_id=encounter.id,
            participant_type="患者本人",
            interaction_type="评估",
            channel_type="文字",
            session_status="进行中",
            started_at=now,
            creator="pytest",
            updator="pytest",
        )
        assessment_instance = AssessmentInstance(
            instance_no=_uid("INSTANCE"),
            task_id=task.id,
            patient_id=patient.id,
            encounter_id=encounter.id,
            scale_id=scale.id,
            scale_version_id=scale_version.id,
            assessment_scene="入院",
            instance_status="待采集",
            patient_name_snapshot=patient.patient_name,
            form_snapshot=scale_version.scale_snapshot,
            creator="pytest",
            updator="pytest",
        )
        db.add_all([option, interaction_session, assessment_instance])
        db.commit()

        return {
            "patient_id": patient.id,
            "encounter_id": encounter.id,
            "task_id": task.id,
            "question_id": question.id,
            "session_id": interaction_session.id,
            "session_no": interaction_session.session_no,
            "instance_id": assessment_instance.id,
        }


def test_multi_submission_preserves_ai_nurse_and_final_answers(postgres_session_factory):
    """同一问题应允许 AI、护士、最终确认三份独立答案。"""
    chain = _seed_domain_chain(postgres_session_factory)
    with postgres_session_factory() as db:
        submissions = []
        for submission_type, submitter_type, value in (
            ("AI抽取", "AI", "65"),
            ("护士独立评估", "护士", "66"),
            ("最终确认", "护士", "66"),
        ):
            submission = AssessmentSubmission(
                submission_no=_uid("SUB"),
                assessment_instance_id=chain["instance_id"],
                submission_type=submission_type,
                submitter_type=submitter_type,
                interaction_session_id=chain["session_id"],
                submission_status="已提交",
                total_question_count=1,
                answered_question_count=1,
                creator="pytest",
                updator="pytest",
            )
            db.add(submission)
            db.flush()
            db.add(
                AssessmentAnswer(
                    submission_id=submission.id,
                    question_id=chain["question_id"],
                    answer_type="整数",
                    answer_number=Decimal(value),
                    value_source=submission_type,
                    creator="pytest",
                    updator="pytest",
                )
            )
            submissions.append(submission)
        db.commit()

        answers = (
            db.query(AssessmentAnswer)
            .filter(AssessmentAnswer.submission_id.in_([item.id for item in submissions]))
            .all()
        )
        assert len(answers) == 3
        assert {answer.answer_number for answer in answers} == {Decimal(65), Decimal(66)}


def test_answer_unique_constraint_is_scoped_to_submission(postgres_session_factory):
    """同一提交不能重复回答同一问题。"""
    chain = _seed_domain_chain(postgres_session_factory)
    with postgres_session_factory() as db:
        submission = AssessmentSubmission(
            submission_no=_uid("SUB"),
            assessment_instance_id=chain["instance_id"],
            submission_type="AI抽取",
            submitter_type="AI",
            submission_status="草稿",
            creator="pytest",
            updator="pytest",
        )
        db.add(submission)
        db.flush()
        for value in ("65", "66"):
            db.add(
                AssessmentAnswer(
                    submission_id=submission.id,
                    question_id=chain["question_id"],
                    answer_type="整数",
                    answer_number=Decimal(value),
                    value_source="AI抽取",
                    creator="pytest",
                    updator="pytest",
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()


def test_message_feedback_unique_per_reviewer(postgres_session_factory):
    """同一护士不能重复标注同一条消息。"""
    chain = _seed_domain_chain(postgres_session_factory)
    now = datetime.now(UTC)
    with postgres_session_factory() as db:
        message = InteractionMessage(
            interaction_session_id=chain["session_id"],
            message_no=_uid("MSG"),
            turn_no=1,
            role_type="AI",
            message_type="文本",
            content_text="请问您今年多大年纪？",
            occurred_at=now,
            creator="pytest",
            updator="pytest",
        )
        db.add(message)
        db.flush()
        for feedback_type in ("like", "dislike"):
            db.add(
                InteractionMessageFeedback(
                    interaction_session_id=chain["session_id"],
                    interaction_message_id=message.id,
                    turn_no=1,
                    reviewer_id=1001,
                    feedback_type=feedback_type,
                    score=5 if feedback_type == "like" else 1,
                    reviewed_at=now,
                    creator="pytest",
                    updator="pytest",
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()


def test_quality_review_persists_dimension_score_and_evidence(postgres_session_factory):
    """整体质量评价应保存模板、维度、分值意见和对话证据。"""
    chain = _seed_domain_chain(postgres_session_factory)
    now = datetime.now(UTC)
    with postgres_session_factory() as db:
        template = QualityReviewTemplate(
            template_code=_uid("QUALITY"),
            template_name="AI对话质量",
            target_type="ai_dialogue",
            score_scale="1-5",
            version_code="v1",
            status="enabled",
            creator="pytest",
            updator="pytest",
        )
        db.add(template)
        db.flush()
        dimension = QualityReviewDimension(
            template_id=template.id,
            dimension_code="follow_up_reasonableness",
            dimension_name="追问合理性",
            dimension_description="异常答案是否被合理追问",
            weight=Decimal("1"),
            max_score=Decimal("5"),
            sort_no=1,
            creator="pytest",
            updator="pytest",
        )
        db.add(dimension)
        db.flush()
        review = QualityReview(
            review_no=_uid("QR"),
            template_id=template.id,
            target_type="ai_dialogue",
            target_id=chain["session_id"],
            patient_id=chain["patient_id"],
            encounter_id=chain["encounter_id"],
            reviewer_id=1001,
            overall_score=Decimal("4"),
            review_comment="整体追问合理",
            issue_tags=[],
            reviewed_at=now,
            creator="pytest",
            updator="pytest",
        )
        db.add(review)
        db.flush()
        db.add(
            QualityReviewScore(
                quality_review_id=review.id,
                dimension_id=dimension.id,
                score_value=Decimal("4"),
                score_comment="应进一步确认症状持续时间",
                evidence_message_ids=["MSG-1"],
                evidence_question_ids=[],
                creator="pytest",
                updator="pytest",
            )
        )
        db.commit()

        persisted = db.query(QualityReviewScore).filter_by(
            quality_review_id=review.id
        ).one()
        assert persisted.score_value == Decimal("4")
        assert persisted.evidence_message_ids == ["MSG-1"]


@pytest.mark.asyncio
async def test_dialog_history_manager_crud_and_logical_delete(postgres_session_factory):
    """管理器应完成消息保存、排序、格式化、上下文和逻辑删除。"""
    chain = _seed_domain_chain(postgres_session_factory)
    manager = DialogHistoryManager(postgres_session_factory)

    first = await manager.save_message(
        chain["session_no"],
        turn_no=1,
        role_type="AI",
        message_type="文本",
        content_text="请问您今年多大年纪？",
        creator="pytest",
    )
    second = await manager.save_message(
        chain["session_no"],
        turn_no=1,
        role_type="患者",
        message_type="文本",
        content_text="我今年65岁。",
        parent_message_id=first.id,
        creator="pytest",
    )

    history = await manager.get_dialog_history(chain["session_no"])
    assert [message.message_no for message in history] == [first.message_no, second.message_no]
    assert await manager.count_messages(chain["session_no"]) == 2
    assert manager.format_for_langchain(history) == [
        {"role": "assistant", "content": "请问您今年多大年纪？"},
        {"role": "user", "content": "我今年65岁。"},
    ]
    assert await manager.get_full_context(chain["session_no"]) == (
        "AI: 请问您今年多大年纪？\n患者: 我今年65岁。\n"
    )

    assert await manager.delete_session_history(chain["session_no"], updator="pytest") == 2
    assert await manager.count_messages(chain["session_no"]) == 0
