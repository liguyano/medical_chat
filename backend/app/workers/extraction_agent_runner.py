"""字段抽取Agent Runner
作用：按会话消费完整对话轮次，并把多量表抽取结果分别写入对应评估实例。
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
from app.models.interaction import InteractionSession
from app.schemas.events import EventType
from app.utils.redis_client import RedisClient
from app.workers.dialog_agent_runner import decode_stream_fields
from app.workers.event_publisher import DialogEventPublisher

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
    """多量表字段抽取编排器。"""

    def __init__(
        self,
        loader: AssessmentQuestionLoader,
        history_manager: DialogHistoryManager,
        writer_factory: type[ExtractionResultWriter],
        redis_client: RedisClient,
        publisher_factory: type[DialogEventPublisher],
        model: BaseChatModel,
    ) -> None:
        self.loader = loader
        self.history_manager = history_manager
        self.writer_factory = writer_factory
        self.redis = redis_client
        self.publisher_factory = publisher_factory
        self.model = model

    async def run(
        self,
        session_id: str,
        scale_codes: list[str],
        check_interval: int = 5,
    ) -> dict[str, Any]:
        """消费对话轮次并增量抽取。"""
        questions = await self.loader.load_questions_by_scale_codes(scale_codes)
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}
        interaction_session_id, task_id, contexts = self._load_contexts(
            session_id,
            scale_codes,
            questions,
        )
        writer = self.writer_factory()
        publisher = self.publisher_factory(session_id, self.redis)
        state_key = f"extraction_agent:state:{session_id}"
        state = self.redis.get(state_key)
        last_event_id = (
            str(state.get("last_event_id"))
            if isinstance(state, dict) and state.get("last_event_id")
            else "0-0"
        )
        total_extracted = 0

        while True:
            messages = self.redis.xread(
                {f"dialog_stream:{session_id}": last_event_id},
                count=20,
                block=check_interval * 1000,
            )
            if not messages:
                continue
            for _, entries in messages:
                for raw_id, raw_fields in entries:
                    last_event_id = (
                        raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
                    )
                    fields = decode_stream_fields(
                        raw_fields,
                        json_fields={"metadata", "tool_calls"},
                    )
                    event_type = fields.get("event_type")
                    if event_type == EventType.SESSION_END.value:
                        self._save_state(state_key, last_event_id)
                        return {
                            "status": "completed",
                            "session_id": session_id,
                            "total_extracted": total_extracted,
                        }
                    if event_type != EventType.DIALOG_TURN.value:
                        self._save_state(state_key, last_event_id)
                        continue

                    history_summary = await self.history_manager.summarize_history(
                        session_id,
                        self.model,
                        max_turns=20,
                    )
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
                                    "turn": int(fields.get("turn_number") or 0),
                                    "message_id": str(fields.get("message_id") or ""),
                                    "patient": str(fields.get("question") or ""),
                                    "ai": str(fields.get("answer") or ""),
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
                            continue
                        valid_ids = {question.question_id for question in context.questions}
                        result.extracted_answers = [
                            answer
                            for answer in result.extracted_answers
                            if answer.question_id in valid_ids
                        ]
                        current_message_id = str(fields.get("message_id") or "")
                        if current_message_id:
                            for answer in result.extracted_answers:
                                if not answer.source_message_ids:
                                    answer.source_message_ids = [current_message_id]
                        if not result.extracted_answers:
                            continue
                        submission = await writer.upsert_submission(
                            interaction_session_id=interaction_session_id,
                            assessment_instance_id=context.instance_id,
                            extraction_result=result,
                            total_question_count=len(context.questions),
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
                        total_extracted += len(result.extracted_answers)
                        question_by_id = {
                            question.question_id: question for question in context.questions
                        }
                        for answer in result.extracted_answers:
                            question = question_by_id[answer.question_id]
                            changed_fields[str(answer.question_id)] = {
                                "question_id": answer.question_id,
                                "question_code": answer.question_code,
                                "question_text": question.question_name,
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
                                "source_message_ids": answer.source_message_ids,
                                "confidence": answer.extraction_confidence,
                                "corrected": False,
                            }
                            confidence_scores[str(answer.question_id)] = (
                                answer.extraction_confidence
                            )

                    if changed_fields:
                        publisher.publish_extraction_result(
                            session_id=session_id,
                            task_id=task_id,
                            extracted_fields=changed_fields,
                            confidence_scores=confidence_scores,
                        )
                    self._save_state(state_key, last_event_id)

    def _load_contexts(
        self,
        session_no: str,
        scale_codes: list[str],
        questions: list[QuestionTask],
    ) -> tuple[int, int, list[ScaleExtractionContext]]:
        """加载会话对应的多量表评估实例。"""
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
    def _find_submission(instance_id: int) -> int | None:
        """查询量表实例已有的AI提交。"""
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

    def _save_state(self, key: str, last_event_id: str) -> None:
        """保存抽取游标。"""
        if not self.redis.set(
            key,
            {"last_event_id": last_event_id},
            ex=3600,
        ):
            raise RuntimeError(f"Extraction Agent状态保存失败: {key}")
