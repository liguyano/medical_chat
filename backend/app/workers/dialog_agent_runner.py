"""Dialog Agent Runner
作用：以Redis会话状态驱动“AI先问、患者回答、AI再问”的第一期文本问诊循环。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models import BaseChatModel
from medagent.agents.factory import create_dialog_agent
from medagent.agents.service_agent.dialog_agent.engine import TextChatEngine
from medagent.agents.service_agent.schedule_agent.models import QuestionTask
from sqlalchemy import select

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import base as model_base
from app.models.assessment_execution import AssessmentInstance
from app.models.interaction import InteractionSession
from app.models.patient_task import CareTask
from app.schemas.events import (
    DialogMessageEvent,
    DialogTurnEvent,
    EventType,
    SessionEndEvent,
)
from app.utils.redis_client import RedisClient
from app.workers.event_publisher import DialogEventPublisher

logger = logging.getLogger(__name__)


def _decode(value: Any) -> Any:
    """解码Redis字节值。"""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def decode_stream_fields(
    fields: dict[bytes, bytes],
    json_fields: set[str] | None = None,
) -> dict[str, Any]:
    """解码Redis Stream扁平字段。"""
    decoded: dict[str, Any] = {}
    for raw_key, raw_value in fields.items():
        key = str(_decode(raw_key))
        value = _decode(raw_value)
        if key in (json_fields or set()) and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        decoded[key] = value
    return decoded


class DialogAgentRunner:
    """AI主导问诊执行器。"""

    def __init__(
        self,
        *,
        session_id: str,
        patient_info: dict[str, Any],
        scale_codes: list[str],
        model: BaseChatModel,
        redis_client: RedisClient,
        state_ttl: int = 3600,
    ) -> None:
        self.session_id = session_id
        self.patient_info = patient_info
        self.scale_codes = scale_codes
        self.model = model
        self.redis = redis_client
        self.state_ttl = state_ttl
        self.stream_key = f"dialog_stream:{session_id}"
        self.state_key = f"dialog_agent:state:{session_id}"
        self.loader = AssessmentQuestionLoader()
        self.history = DialogHistoryManager()
        self.publisher = DialogEventPublisher(session_id, redis_client)
        self.task_id = 0
        self.interaction_session_id = 0

    async def run(self, check_interval: int = 5) -> dict[str, Any]:
        """执行可恢复的文本问诊循环。"""
        questions = await self.loader.load_questions_by_scale_codes(self.scale_codes)
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}
        self._load_session_context()
        state = self._restore_state() or {
            "current_question_index": 0,
            "turn_counter": 0,
            "last_event_id": "0-0",
        }
        current_index = int(state["current_question_index"])
        turn_counter = int(state["turn_counter"])
        last_event_id = str(state["last_event_id"])

        if turn_counter == 0:
            await self._publish_question(
                question=questions[0],
                text=questions[0].patient_text or questions[0].question_name,
                turn_no=1,
                is_opening=True,
            )
            turn_counter = 1
            current_index = 0
            self._save_state(current_index, turn_counter, last_event_id)

        idle_reads = 0
        while True:
            messages = self.redis.xread(
                {self.stream_key: last_event_id},
                count=20,
                block=check_interval * 1000,
            )
            if not messages:
                idle_reads += 1
                if idle_reads >= 60:
                    return {
                        "status": "timeout",
                        "session_id": self.session_id,
                        "total_turns": turn_counter,
                    }
                continue
            idle_reads = 0
            for _, entries in messages:
                for raw_id, raw_fields in entries:
                    last_event_id = str(_decode(raw_id))
                    fields = decode_stream_fields(
                        raw_fields,
                        json_fields={"metadata", "tool_calls"},
                    )
                    if fields.get("event_type") != EventType.PATIENT_ANSWER.value:
                        self._save_state(current_index, turn_counter, last_event_id)
                        continue
                    event_turn = int(fields.get("turn_number") or turn_counter)
                    if event_turn < turn_counter:
                        self._save_state(current_index, turn_counter, last_event_id)
                        continue

                    patient_answer = str(fields.get("content") or "").strip()
                    if not patient_answer:
                        self._save_state(current_index, turn_counter, last_event_id)
                        continue

                    if current_index + 1 >= len(questions):
                        self.publisher.publish(
                            DialogTurnEvent(
                                session_id=self.session_id,
                                task_id=self.task_id,
                                message_id=str(fields.get("message_id") or "") or None,
                                turn_number=turn_counter,
                                question=patient_answer,
                                answer="",
                                metadata={
                                    "asked_question_id": questions[current_index].question_id,
                                    "completed": True,
                                },
                            )
                        )
                        self._complete_session(turn_counter)
                        self.publisher.publish(
                            SessionEndEvent(
                                session_id=self.session_id,
                                task_id=self.task_id,
                                end_reason="completed",
                                total_turns=turn_counter,
                                duration_seconds=0,
                            )
                        )
                        self._save_state(current_index, turn_counter, last_event_id)
                        return {
                            "status": "completed",
                            "session_id": self.session_id,
                            "total_turns": turn_counter,
                        }

                    next_index = current_index + 1
                    next_question = questions[next_index]
                    agent = await self._build_agent(
                        questions=questions,
                        turn_no=turn_counter,
                        patient_answer=patient_answer,
                        next_question=next_question,
                    )
                    try:
                        generated_text = await agent.handle_patient_input(
                            patient_answer,
                            session_no=None,
                            context_metadata={
                                "task_id": self.task_id,
                                "message_id": fields.get("message_id"),
                                "metadata": {
                                    "asked_question_id": questions[current_index].question_id,
                                    "next_question_id": next_question.question_id,
                                },
                            },
                        )
                    finally:
                        await agent.close()

                    constraints = list(agent.last_turn_context.get("constraints") or [])
                    target_text = next_question.patient_text or next_question.question_name
                    next_text = (
                        generated_text.strip()
                        if constraints and generated_text.strip()
                        else target_text
                    )
                    self.publisher.publish(
                        DialogTurnEvent(
                            session_id=self.session_id,
                            task_id=self.task_id,
                            message_id=str(fields.get("message_id") or "") or None,
                            turn_number=turn_counter,
                            question=patient_answer,
                            answer=next_text,
                            tool_calls=list(agent.last_turn_context.get("tool_calls") or [])
                            or None,
                            metadata={
                                "asked_question_id": questions[current_index].question_id,
                                "next_question_id": next_question.question_id,
                                "constraint_applied": bool(constraints),
                            },
                        )
                    )
                    turn_counter += 1
                    current_index = next_index
                    await self._publish_question(
                        question=next_question,
                        text=next_text,
                        turn_no=turn_counter,
                        is_opening=False,
                    )
                    self._save_state(current_index, turn_counter, last_event_id)

    def _load_session_context(self) -> None:
        """解析会话主键和任务主键。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            session = db.scalar(
                select(InteractionSession).where(
                    InteractionSession.session_no == self.session_id,
                    InteractionSession.deleted == 0,
                )
            )
            if session is None:
                raise RuntimeError(f"交互会话不存在: {self.session_id}")
            self.task_id = session.task_id
            self.interaction_session_id = session.id

    async def _build_agent(
        self,
        *,
        questions: list[QuestionTask],
        turn_no: int,
        patient_answer: str,
        next_question: QuestionTask,
    ):
        """按数据库历史重建文本Agent。"""
        from app.workers.dialog_agent_runtime import get_runtime_dependencies

        deps = get_runtime_dependencies(self.session_id)
        agent = create_dialog_agent(
            session_id=self.session_id,
            patient_info=self.patient_info,
            task_list=questions,
            engine_type="text",
            agent_name="dialog_agent",
            middlewares=deps["middlewares"],
            state_store=deps["state_store"],
            history_store=deps["history_store"],
            tool_executor=deps["tool_executor"],
        )
        await agent.initialize()
        agent.turn_counter = turn_no - 1
        history = await self.history.get_dialog_history(self.session_id)
        formatted = self.history.format_for_langchain(history)
        if (
            formatted
            and formatted[-1]["role"] == "user"
            and formatted[-1]["content"] == patient_answer
        ):
            formatted = formatted[:-1]
        if isinstance(agent.engine, TextChatEngine):
            agent.engine.messages.extend(formatted)
        await agent.engine.update_session(
            instructions=(
                "你正在执行护理量表问诊。患者回答后，只输出一个简洁的下一问。"
                "若Schedule约束要求追问，先完成追问；否则必须询问以下目标题目，不得回答患者、"
                f"不得一次询问多题：{next_question.patient_text or next_question.question_name}"
            )
        )
        return agent

    async def _publish_question(
        self,
        *,
        question: QuestionTask,
        text: str,
        turn_no: int,
        is_opening: bool,
    ) -> None:
        """保存并发布AI问诊问题。"""
        message = await self.history.save_message(
            self.session_id,
            turn_no=turn_no,
            role_type="AI",
            message_type="文本",
            content_text=text,
            intent_type="提问",
            related_question_id=question.question_id,
            creator="dialog_agent",
        )
        self.publisher.publish(
            DialogMessageEvent(
                session_id=self.session_id,
                task_id=self.task_id,
                message_id=message.message_no,
                turn_number=turn_no,
                role="assistant",
                content=text,
                question_id=str(question.question_id),
                is_opening=is_opening,
            )
        )

    def _complete_session(self, turn_counter: int) -> None:
        """完成会话、任务和评估实例状态。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        now = datetime.now(UTC)
        with model_base.SessionLocal() as db:
            session = db.get(InteractionSession, self.interaction_session_id)
            task = db.get(CareTask, self.task_id)
            if session is not None:
                session.session_status = "completed"
                session.ended_at = now
                session.updator = "dialog_agent"
            if task is not None:
                task.task_status = "pending_review"
                task.completed_at = now
                task.updator = "dialog_agent"
            instances = list(
                db.scalars(
                    select(AssessmentInstance).where(
                        AssessmentInstance.task_id == self.task_id,
                        AssessmentInstance.deleted == 0,
                    )
                ).all()
            )
            for instance in instances:
                instance.instance_status = "ai_completed"
                instance.assessed_at = now
                instance.updator = "dialog_agent"
            db.commit()
        logger.info(
            "AI问诊完成: session=%s turns=%s",
            self.session_id,
            turn_counter,
        )

    def _restore_state(self) -> dict[str, Any] | None:
        """恢复Redis运行状态。"""
        state = self.redis.get(self.state_key)
        return state if isinstance(state, dict) else None

    def _save_state(
        self,
        current_question_index: int,
        turn_counter: int,
        last_event_id: str,
    ) -> None:
        """保存Redis运行状态。"""
        saved = self.redis.set(
            self.state_key,
            {
                "current_question_index": current_question_index,
                "turn_counter": turn_counter,
                "last_event_id": last_event_id,
            },
            ex=self.state_ttl,
        )
        if not saved:
            raise RuntimeError(f"Dialog Agent状态保存失败: {self.state_key}")
