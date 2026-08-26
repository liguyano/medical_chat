"""字段抽取 Agent 单轮运行器
作用：按需创建抽取 Agent，处理一条患者答案并增量写入评估结果。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from medagent.agents.factory import create_extraction_agent
from medagent.agents.service_agent.schedule_agent.models import QuestionTask
from sqlalchemy import select

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.managers.extraction_result_writer import ExtractionResultWriter
from app.models import base as model_base
from app.models.assessment_execution import AssessmentInstance, AssessmentSubmission
from app.models.assessment_template import AssessmentScale, AssessmentScaleVersion
from app.models.interaction import InteractionMessage, InteractionSession
from app.models.patient_task import CareTask
from app.schemas.events import AgentErrorEvent, ProgressUpdatedEvent
from app.services.assessment_progress_service import refresh_assessment_progress
from app.utils.redis_client import RedisClient
from app.workers.event_publisher import DialogEventPublisher
from app.workers.worker_lease import WorkerLease

logger = logging.getLogger(__name__)


@dataclass
class ScaleExtractionContext:
    """单量表抽取上下文。"""

    scale_code: str
    scale_name: str
    version_code: str
    scale_version_id: int
    instance_id: int
    questions: list[QuestionTask]


class ExtractionAgentRunner:
    """多量表字段抽取单轮编排器。"""

    def __init__(
        self,
        loader: AssessmentQuestionLoader,
        history_manager: DialogHistoryManager,
        writer_factory: type[ExtractionResultWriter],
        redis_client: RedisClient,
        publisher_factory: type[DialogEventPublisher],
        model: BaseChatModel,
        state_ttl: int = 86400,
    ) -> None:
        self.loader = loader
        self.history_manager = history_manager
        self.writer_factory = writer_factory
        self.redis = redis_client
        self.publisher_factory = publisher_factory
        self.model = model
        self.state_ttl = state_ttl

    async def run(
        self,
        session_id: str,
        scale_codes: list[str],
        *,
        source_message_id: str | None = None,
        source_event_id: str | None = None,
        check_interval: int = 1,
    ) -> dict[str, Any]:
        """抽取一条患者答案并持久化。"""
        if not scale_codes:
            return {"status": "failed", "reason": "missing_scale_codes"}
        if not source_message_id:
            return {
                "status": "skipped",
                "reason": "opening_does_not_require_extraction",
                "session_id": session_id,
            }

        questions = await self.loader.load_questions_by_scale_codes(scale_codes)
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}
        interaction_session_id, task_id, contexts = self._load_contexts(
            session_id,
            scale_codes,
            questions,
        )
        lease = WorkerLease(
            self.redis,
            agent_name="extraction_agent",
            session_id=session_id,
            work_id=source_message_id,
        )
        if not lease.acquire():
            return {
                "status": "already_running",
                "session_id": session_id,
                "source_message_id": source_message_id,
            }

        state_key = f"extraction_agent:state:{session_id}"
        try:
            state = self.redis.get(state_key)
            state = state if isinstance(state, dict) else {}
            processed = list(state.get("processed_message_ids") or [])
            if source_message_id in processed:
                return {
                    "status": "already_completed",
                    "session_id": session_id,
                    "source_message_id": source_message_id,
                }

            patient_message = self._load_patient_message(
                interaction_session_id,
                source_message_id,
            )
            asked_message = self._load_ai_message(
                interaction_session_id,
                patient_message.turn_no,
            )
            history_summary = await self.history_manager.summarize_history(
                session_id,
                self.model,
                max_turns=20,
            )
            writer = self.writer_factory()
            changed_fields: dict[str, Any] = {}
            confidence_scores: dict[str, float] = {}

            for context in contexts:
                submission_id = self._find_submission(context.instance_id)
                previous = (
                    await writer.get_previous_extraction(submission_id)
                    if submission_id
                    else {}
                )
                agent = create_extraction_agent(
                    session_id=session_id,
                    scale_codes=[context.scale_code],
                    model=self.model,
                )
                result = await agent.extract_with_retry(
                    previous_extraction=previous,
                    history_summary=history_summary,
                    new_dialog=[
                        {
                            "turn": patient_message.turn_no,
                            "message_id": source_message_id,
                            "patient": str(
                                patient_message.content_text
                                or patient_message.asr_text
                                or ""
                            ),
                            "ai_question": str(
                                asked_message.content_text if asked_message else ""
                            ),
                        }
                    ],
                    scale_version={
                        "scale_name": context.scale_name,
                        "version_code": context.version_code,
                    },
                    questions=[
                        {
                            "question_id": question.question_id,
                            "question_code": question.question_code,
                            "question_text": (
                                question.patient_text or question.question_name
                            ),
                            "answer_type": question.question_type,
                            "options": [
                                option.model_dump(mode="json")
                                for option in question.options
                            ],
                            "scoring_rules": {},
                            "required": question.required,
                        }
                        for question in context.questions
                    ],
                    max_retries=3,
                )
                if result is None:
                    reason = f"字段抽取失败，已达到重试次数: {context.scale_code}"
                    self.publisher_factory(session_id, self.redis).publish(
                        AgentErrorEvent(
                            session_id=session_id,
                            task_id=task_id,
                            message_id=source_message_id,
                            agent_name="extraction_agent",
                            error_code="EXTRACTION_RETRY_EXHAUSTED",
                            message="字段抽取重试已达上限，等待后续对话重新解析",
                            retrying=False,
                            manual_intervention=False,
                            intervention_reason=reason,
                        )
                    )
                    return {
                        "status": "failed",
                        "session_id": session_id,
                        "task_id": task_id,
                        "reason": reason,
                    }

                valid_ids = {question.question_id for question in context.questions}
                for invalid in result.invalid_answers:
                    logger.warning(
                        "[Extraction Agent] 跳过无效候选: session=%s scale=%s "
                        "question=%s error=%s",
                        session_id,
                        context.scale_code,
                        invalid.question_id,
                        invalid.error,
                    )
                result.extracted_answers = [
                    answer
                    for answer in result.extracted_answers
                    if answer.question_id in valid_ids
                    and self._has_extracted_value(answer)
                ]
                for answer in result.extracted_answers:
                    if not answer.source_message_ids:
                        answer.source_message_ids = [source_message_id]
                if not result.extracted_answers:
                    continue

                submission = await writer.upsert_submission(
                    interaction_session_id=interaction_session_id,
                    assessment_instance_id=context.instance_id,
                    extraction_result=result,
                    total_question_count=len(context.questions),
                    invalid_answers=[],
                )
                answers = await writer.upsert_answers(
                    submission_id=submission.id,
                    extracted_answers=result.extracted_answers,
                )
                for answer, stored in zip(result.extracted_answers, answers):
                    await writer.upsert_answer_options(
                        answer_id=stored.id,
                        question_id=answer.question_id,
                        selected_option_codes=answer.selected_option_codes,
                        extra_inputs=answer.extra_inputs,
                    )
                await writer.calculate_scores(
                    submission_id=submission.id,
                    scale_version_id=context.scale_version_id,
                )

                question_by_id = {
                    question.question_id: question for question in context.questions
                }
                for answer in result.extracted_answers:
                    question = question_by_id[answer.question_id]
                    selected_definitions = {
                        option.option_code: option
                        for option in question.options
                    }
                    selected_labels = [
                        selected_definitions[code].option_label
                        for code in answer.selected_option_codes
                        if code in selected_definitions
                    ]
                    selected_values = [
                        str(selected_definitions[code].option_value)
                        for code in answer.selected_option_codes
                        if code in selected_definitions
                    ]
                    display_value = (
                        "、".join(selected_labels)
                        if selected_labels
                        else (
                            str(answer.answer_value)
                            if answer.answer_value is not None
                            else None
                        )
                    )
                    changed_fields[str(answer.question_id)] = {
                        "question_id": answer.question_id,
                        "question_code": answer.question_code,
                        "answer_type": answer.answer_type,
                        "question_text": (
                            question.patient_text or question.question_name
                        ),
                        "answer_text": (
                            str(answer.answer_value)
                            if answer.answer_type == "text"
                            and answer.answer_value is not None
                            else None
                        ),
                        "answer_number": (
                            float(answer.answer_value)
                            if answer.answer_type == "number"
                            and answer.answer_value is not None
                            else None
                        ),
                        "answer_boolean": (
                            bool(answer.answer_value)
                            if answer.answer_type == "boolean"
                            and answer.answer_value is not None
                            else None
                        ),
                        "selected_options": answer.selected_option_codes,
                        "selected_option_labels": selected_labels or None,
                        "selected_option_values": selected_values or None,
                        "options": [
                            {
                                "code": option.option_code,
                                "label": option.option_label,
                                "value": option.option_value,
                                "score": (
                                    float(option.clinical_score)
                                    if option.clinical_score is not None
                                    else None
                                ),
                            }
                            for option in question.options
                        ],
                        "display_value": display_value,
                        "source_message_ids": answer.source_message_ids,
                        "confidence": answer.extraction_confidence,
                        "corrected": False,
                    }
                    confidence_scores[str(answer.question_id)] = (
                        answer.extraction_confidence
                    )

            if changed_fields:
                self.publisher_factory(session_id, self.redis).publish_extraction_result(
                    session_id=session_id,
                    task_id=task_id,
                    extracted_fields=changed_fields,
                    confidence_scores=confidence_scores,
                    message_id=source_message_id,
                )
            if model_base.SessionLocal is None:
                raise RuntimeError("数据库未初始化")
            with model_base.SessionLocal() as db:
                progress = refresh_assessment_progress(db, session_id)
            publisher = self.publisher_factory(session_id, self.redis)
            publisher.publish(
                ProgressUpdatedEvent(
                    session_id=session_id,
                    task_id=task_id,
                    message_id=source_message_id,
                    current=progress.current,
                    total=progress.total,
                    completed=progress.completed,
                    remaining_question_ids=list(progress.remaining_question_ids),
                )
            )
            processed.append(source_message_id)
            if not self.redis.set(
                state_key,
                {
                    "last_event_id": source_event_id or state.get("last_event_id") or "0-0",
                    "processed_message_ids": processed[-100:],
                },
                ex=self.state_ttl,
            ):
                raise RuntimeError(f"Extraction Agent 状态保存失败: {state_key}")
            return {
                "status": "turn_completed",
                "session_id": session_id,
                "source_message_id": source_message_id,
                "field_count": len(changed_fields),
                "progress_current": progress.current,
                "progress_total": progress.total,
                "assessment_completed": progress.completed,
                "manual_intervention": False,
            }
        except Exception:
            DialogEventPublisher(session_id, self.redis).publish(
                AgentErrorEvent(
                    session_id=session_id,
                    task_id=task_id,
                    message_id=source_message_id,
                    agent_name="extraction_agent",
                    error_code="EXTRACTION_FAILED",
                    message="字段抽取失败，后台正在重试",
                    retrying=True,
                )
            )
            raise
        finally:
            lease.release()

    def _load_contexts(
        self,
        session_no: str,
        scale_codes: list[str],
        questions: list[QuestionTask],
    ) -> tuple[int, int, list[ScaleExtractionContext]]:
        """加载会话对应的量表评估实例。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            session = db.scalar(
                select(InteractionSession).where(
                    InteractionSession.session_no == session_no,
                    InteractionSession.deleted == 0,
                )
            )
            if session is None:
                raise RuntimeError(f"交互会话不存在: {session_no}")
            rows = db.execute(
                select(AssessmentInstance, AssessmentScale, AssessmentScaleVersion)
                .join(AssessmentScale, AssessmentScale.id == AssessmentInstance.scale_id)
                .join(
                    AssessmentScaleVersion,
                    AssessmentScaleVersion.id == AssessmentInstance.scale_version_id,
                )
                .where(
                    AssessmentInstance.task_id == session.task_id,
                    AssessmentScale.scale_code.in_(scale_codes),
                    AssessmentInstance.deleted == 0,
                )
            ).all()
            contexts = [
                ScaleExtractionContext(
                    scale_code=scale.scale_code,
                    scale_name=scale.scale_name,
                    version_code=version.version_code,
                    scale_version_id=version.id,
                    instance_id=instance.id,
                    questions=[
                        question
                        for question in questions
                        if question.scale_code == scale.scale_code
                    ],
                )
                for instance, scale, version in rows
            ]
            if len(contexts) != len(scale_codes):
                raise RuntimeError("会话评估实例与所选量表不一致")
            return session.id, session.task_id, contexts

    @staticmethod
    def _has_extracted_value(answer: Any) -> bool:
        """判断模型抽取项是否包含可持久化的实际答案。"""
        if answer.selected_option_codes:
            return True
        if isinstance(answer.answer_value, str):
            return bool(answer.answer_value.strip())
        return answer.answer_value is not None

    @staticmethod
    def _find_submission(instance_id: int) -> int | None:
        """查询量表实例已有的 AI 抽取提交。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            return db.scalar(
                select(AssessmentSubmission.id).where(
                    AssessmentSubmission.assessment_instance_id == instance_id,
                    AssessmentSubmission.submission_type == "ai_extraction",
                    AssessmentSubmission.deleted == 0,
                )
            )

    @staticmethod
    def _load_patient_message(
        interaction_session_id: int,
        message_no: str,
    ) -> InteractionMessage:
        """读取患者答案消息。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            message = db.scalar(
                select(InteractionMessage).where(
                    InteractionMessage.interaction_session_id
                    == interaction_session_id,
                    InteractionMessage.message_no == message_no,
                    InteractionMessage.role_type.in_(["患者", "家属", "user"]),
                    InteractionMessage.deleted == 0,
                )
            )
            if message is None:
                raise RuntimeError(f"患者答案不存在: {message_no}")
            db.expunge(message)
            return message

    @staticmethod
    def _load_ai_message(
        interaction_session_id: int,
        turn_no: int,
    ) -> InteractionMessage | None:
        """读取患者答案对应的 AI 问句。"""
        if model_base.SessionLocal is None:
            return None
        with model_base.SessionLocal() as db:
            message = db.scalar(
                select(InteractionMessage)
                .where(
                    InteractionMessage.interaction_session_id
                    == interaction_session_id,
                    InteractionMessage.turn_no == turn_no,
                    InteractionMessage.role_type.in_(["AI", "assistant"]),
                    InteractionMessage.deleted == 0,
                )
                .order_by(InteractionMessage.id.desc())
            )
            if message is not None:
                db.expunge(message)
            return message
