"""Dialog Agent 单轮运行器
作用：按需创建文本 Agent，生成首问或消费一条患者答案，并在任务结束后释放实例。
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from medagent.agents.factory import create_dialog_agent
from medagent.agents.service_agent.dialog_agent.agent import GENERIC_ERROR_MESSAGE
from medagent.agents.service_agent.dialog_agent.engine import TextChatEngine
from medagent.agents.service_agent.schedule_agent.models import QuestionTask
from sqlalchemy import select

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import base as model_base
from app.models.assessment_execution import AssessmentInstance
from app.models.interaction import InteractionMessage, InteractionSession
from app.models.patient_task import CareTask
from app.schemas.events import (
    AgentErrorEvent,
    AssistantMessageStartedEvent,
    DialogMessageEvent,
    DialogTextEvent,
    DialogTurnEvent,
    SessionEndEvent,
)
from app.utils.redis_client import RedisClient
from app.workers.dialog_output_store import DialogOutputStore
from app.workers.event_publisher import DialogEventPublisher
from app.workers.worker_lease import WorkerLease

logger = logging.getLogger(__name__)


def _decode(value: Any) -> Any:
    """解码 Redis 字节值。"""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def decode_stream_fields(
    fields: dict[bytes, bytes],
    json_fields: set[str] | None = None,
) -> dict[str, Any]:
    """解码 Redis Stream 扁平字段。"""
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
    """AI 主导问诊单轮执行器。"""

    def __init__(
        self,
        *,
        session_id: str,
        patient_info: dict[str, Any],
        scale_codes: list[str],
        model: BaseChatModel,
        redis_client: RedisClient,
        state_ttl: int = 86400,
    ) -> None:
        self.session_id = session_id
        self.patient_info = patient_info
        self.scale_codes = scale_codes
        self.model = model
        self.redis = redis_client
        self.state_ttl = state_ttl
        self.state_key = f"dialog_agent:state:{session_id}"
        self.loader = AssessmentQuestionLoader()
        self.history = DialogHistoryManager()
        self.publisher = DialogEventPublisher(session_id, redis_client)
        self.output_store = DialogOutputStore(redis_client, ttl=state_ttl)
        self.task_id = 0
        self.interaction_session_id = 0

    async def run(
        self,
        *,
        source_message_id: str | None = None,
        source_event_id: str | None = None,
    ) -> dict[str, Any]:
        """生成首问或处理一条患者答案
        作用：每次 Celery 调用只处理一个工作单元，不在任务内长驻等待 Redis Stream。
        Args:
            - source_message_id: 患者答案消息编号；为空时生成首问。
            - source_event_id: 患者答案在 Redis Stream 中的事件游标。
        Return:
            - 当前工作单元的执行状态。
        """
        questions = await self.loader.load_questions_by_scale_codes(self.scale_codes)
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}
        self._load_session_context()

        work_id = source_message_id or "opening"
        lease = WorkerLease(
            self.redis,
            agent_name="dialog_agent",
            session_id=self.session_id,
            work_id=work_id,
        )
        if not lease.acquire():
            return {
                "status": "already_running",
                "session_id": self.session_id,
                "work_id": work_id,
            }

        try:
            state = self._restore_state() or self._rebuild_state_from_history(questions)
            if source_message_id is None:
                return await self._run_opening(questions, state)
            return await self._run_answer(
                questions=questions,
                state=state,
                source_message_id=source_message_id,
                source_event_id=source_event_id,
            )
        finally:
            lease.release()

    async def _run_opening(
        self,
        questions: list[QuestionTask],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """生成首个 AI 问诊问题。"""
        existing = self._find_ai_message(turn_no=1)
        if existing is not None:
            self._ensure_completed_snapshot(
                message=existing,
                question_id=existing.related_question_id,
                is_opening=True,
            )
            self._save_state(
                current_question_index=0,
                turn_counter=1,
                last_event_id=str(state.get("last_event_id") or "0-0"),
                processed_message_ids=list(state.get("processed_message_ids") or []),
            )
            return {
                "status": "already_completed",
                "session_id": self.session_id,
                "message_id": existing.message_no,
            }

        question = questions[0]
        generation_id, message_id = self._generation_ids("opening")
        started_event_id = self._start_generation(
            generation_id=generation_id,
            message_id=message_id,
            turn_number=1,
            question_id=question.question_id,
        )

        async def on_delta(text_chunk: str) -> None:
            self._publish_text_delta(
                generation_id=generation_id,
                message_id=message_id,
                turn_number=1,
                question_id=question.question_id,
                text_chunk=text_chunk,
            )

        try:
            opening_text = await self._generate_opening_question(
                question,
                on_delta=on_delta,
            )
            message, completed_event_id = await self._persist_completed_question(
                question=question,
                text=opening_text,
                turn_no=1,
                is_opening=True,
                generation_id=generation_id,
                message_id=message_id,
            )
            self.output_store.complete(
                session_id=self.session_id,
                message_id=message_id,
                content=opening_text,
                last_event_id=completed_event_id,
            )
            self._save_state(
                current_question_index=0,
                turn_counter=1,
                last_event_id=completed_event_id or started_event_id or "0-0",
                processed_message_ids=[],
            )
            return {
                "status": "opening_completed",
                "session_id": self.session_id,
                "message_id": message.message_no,
            }
        except Exception as exc:
            self._mark_generation_failed(
                message_id=message_id,
                generation_id=generation_id,
                exc=exc,
            )
            raise

    async def _run_answer(
        self,
        *,
        questions: list[QuestionTask],
        state: dict[str, Any],
        source_message_id: str,
        source_event_id: str | None,
    ) -> dict[str, Any]:
        """消费一条已落库的患者答案并生成下一问。"""
        processed = list(state.get("processed_message_ids") or [])
        patient_message = self._load_patient_message(source_message_id)
        current_index = self._resolve_current_question_index(patient_message, questions)

        existing_next = self._find_ai_message(turn_no=patient_message.turn_no + 1)
        if source_message_id in processed or existing_next is not None:
            if existing_next is not None:
                self._ensure_completed_snapshot(
                    message=existing_next,
                    question_id=existing_next.related_question_id,
                    is_opening=False,
                )
            if source_message_id not in processed:
                processed.append(source_message_id)
            self._save_state(
                current_question_index=(
                    self._question_index(existing_next.related_question_id, questions)
                    if existing_next is not None
                    else current_index
                ),
                turn_counter=(
                    existing_next.turn_no
                    if existing_next is not None
                    else patient_message.turn_no
                ),
                last_event_id=source_event_id or str(state.get("last_event_id") or "0-0"),
                processed_message_ids=processed,
            )
            return {
                "status": "already_completed",
                "session_id": self.session_id,
                "source_message_id": source_message_id,
            }

        patient_answer = str(
            patient_message.content_text or patient_message.asr_text or ""
        ).strip()
        if not patient_answer:
            raise RuntimeError(f"患者答案为空: {source_message_id}")

        if current_index + 1 >= len(questions):
            self.publisher.publish(
                DialogTurnEvent(
                    session_id=self.session_id,
                    task_id=self.task_id,
                    message_id=source_message_id,
                    turn_number=patient_message.turn_no,
                    question=patient_answer,
                    answer="",
                    metadata={
                        "asked_question_id": questions[current_index].question_id,
                        "completed": True,
                    },
                )
            )
            self._complete_session(patient_message.turn_no)
            end_event_id = self.publisher.publish(
                SessionEndEvent(
                    session_id=self.session_id,
                    task_id=self.task_id,
                    end_reason="completed",
                    total_turns=patient_message.turn_no,
                    duration_seconds=0,
                )
            )
            processed.append(source_message_id)
            self._save_state(
                current_question_index=current_index,
                turn_counter=patient_message.turn_no,
                last_event_id=end_event_id or source_event_id or "0-0",
                processed_message_ids=processed,
            )
            return {
                "status": "completed",
                "session_id": self.session_id,
                "total_turns": patient_message.turn_no,
            }

        next_index = current_index + 1
        next_question = questions[next_index]
        next_turn = patient_message.turn_no + 1
        generation_id, message_id = self._generation_ids(source_message_id)
        started_event_id = self._start_generation(
            generation_id=generation_id,
            message_id=message_id,
            turn_number=next_turn,
            question_id=next_question.question_id,
        )

        async def text_delta_sink(text_chunk: str, _context: dict[str, Any]) -> None:
            self._publish_text_delta(
                generation_id=generation_id,
                message_id=message_id,
                turn_number=next_turn,
                question_id=next_question.question_id,
                text_chunk=text_chunk,
            )

        agent = None
        try:
            agent = await self._build_agent(
                questions=questions,
                turn_no=patient_message.turn_no,
                patient_answer=patient_answer,
                next_question=next_question,
                text_delta_sink=text_delta_sink,
            )
            generated_text = await agent.handle_patient_input(
                patient_answer,
                session_no=None,
                context_metadata={
                    "task_id": self.task_id,
                    "message_id": source_message_id,
                    "metadata": {
                        "asked_question_id": questions[current_index].question_id,
                        "next_question_id": next_question.question_id,
                    },
                },
            )
            next_text = generated_text.strip()
            if not next_text or next_text == GENERIC_ERROR_MESSAGE:
                raise RuntimeError("Dialog Agent 真实模型未返回有效问句")

            message, completed_event_id = await self._persist_completed_question(
                question=next_question,
                text=next_text,
                turn_no=next_turn,
                is_opening=False,
                generation_id=generation_id,
                message_id=message_id,
            )
            self.output_store.complete(
                session_id=self.session_id,
                message_id=message_id,
                content=next_text,
                last_event_id=completed_event_id,
            )
            processed.append(source_message_id)
            self._save_state(
                current_question_index=next_index,
                turn_counter=next_turn,
                last_event_id=(
                    completed_event_id
                    or started_event_id
                    or source_event_id
                    or "0-0"
                ),
                processed_message_ids=processed[-100:],
            )
            return {
                "status": "turn_completed",
                "session_id": self.session_id,
                "source_message_id": source_message_id,
                "message_id": message.message_no,
                "turn_number": next_turn,
            }
        except Exception as exc:
            self._mark_generation_failed(
                message_id=message_id,
                generation_id=generation_id,
                exc=exc,
            )
            raise
        finally:
            if agent is not None:
                await agent.close()

    async def _generate_opening_question(
        self,
        question: QuestionTask,
        *,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """使用真实模型流式生成首个问诊问题。"""
        target_text = question.patient_text or question.question_name
        model_name = getattr(self.model, "model_name", None) or getattr(
            self.model,
            "model",
            "unknown",
        )
        logger.info(
            "[Dialog Agent] 调用真实模型生成首问: session=%s, model=%s, question=%s",
            self.session_id,
            model_name,
            question.question_code,
        )
        messages = [
            SystemMessage(
                content=(
                    "你是住院病区的护理人员，正在开始一次护理评估问诊。"
                    "请用自然、礼貌、简洁的中文开场，并且只询问一个问题。"
                    "不要回答患者，不要解释量表，不要一次询问多项内容。"
                )
            ),
            HumanMessage(
                content=(
                    f"患者姓名：{self.patient_info.get('name', '患者')}。"
                    f"本轮必须询问的目标题目：{target_text}"
                )
            ),
        ]

        chunks: list[str] = []
        stream = getattr(self.model, "astream", None)
        if callable(stream):
            async for chunk in stream(messages):
                text = self._message_content(chunk)
                if not text:
                    continue
                chunks.append(text)
                if on_delta:
                    await on_delta(text)
        else:
            response = await self.model.ainvoke(messages)
            text = self._message_content(response)
            if text:
                chunks.append(text)
                if on_delta:
                    await on_delta(text)

        opening_text = "".join(chunks).strip()
        if not opening_text:
            raise RuntimeError("Dialog Agent 真实模型未返回首问")
        logger.info(
            "[Dialog Agent] 真实模型首问生成成功: session=%s, model=%s, length=%s",
            self.session_id,
            model_name,
            len(opening_text),
        )
        return opening_text

    @staticmethod
    def _message_content(message: Any) -> str:
        """提取 LangChain 消息或消息分块中的文本。"""
        content = getattr(message, "content", "")
        if isinstance(content, list):
            return "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict)
            )
        return str(content or "")

    def _start_generation(
        self,
        *,
        generation_id: str,
        message_id: str,
        turn_number: int,
        question_id: int,
    ) -> str | None:
        """初始化快照并发布 AI 消息开始事件。"""
        self.output_store.start(
            session_id=self.session_id,
            task_id=self.task_id,
            message_id=message_id,
            generation_id=generation_id,
            turn_number=turn_number,
            question_id=question_id,
        )
        event_id = self.publisher.publish(
            AssistantMessageStartedEvent(
                session_id=self.session_id,
                task_id=self.task_id,
                message_id=message_id,
                turn_number=turn_number,
                generation_id=generation_id,
                question_id=str(question_id),
            )
        )
        self.output_store.append(
            session_id=self.session_id,
            message_id=message_id,
            text_chunk="",
            last_event_id=event_id,
        )
        return event_id

    def _publish_text_delta(
        self,
        *,
        generation_id: str,
        message_id: str,
        turn_number: int,
        question_id: int,
        text_chunk: str,
    ) -> None:
        """写入完整快照并发布单个模型文本增量。"""
        self.output_store.append(
            session_id=self.session_id,
            message_id=message_id,
            text_chunk=text_chunk,
        )
        event_id = self.publisher.publish(
            DialogTextEvent(
                session_id=self.session_id,
                task_id=self.task_id,
                message_id=message_id,
                turn_number=turn_number,
                text_chunk=text_chunk,
                generation_id=generation_id,
                question_id=str(question_id),
                is_final=False,
            )
        )
        if event_id:
            self.output_store.append(
                session_id=self.session_id,
                message_id=message_id,
                text_chunk="",
                last_event_id=event_id,
            )

    async def _persist_completed_question(
        self,
        *,
        question: QuestionTask,
        text: str,
        turn_no: int,
        is_opening: bool,
        generation_id: str,
        message_id: str,
    ) -> tuple[InteractionMessage, str | None]:
        """保存 AI 完整问句并发布完成事件。"""
        message = await self.history.save_message(
            self.session_id,
            message_no=message_id,
            turn_no=turn_no,
            role_type="AI",
            message_type="文本",
            content_text=text,
            intent_type="提问",
            related_question_id=question.question_id,
            creator="dialog_agent",
        )
        event_id = self.publisher.publish(
            DialogMessageEvent(
                session_id=self.session_id,
                task_id=self.task_id,
                message_id=message.message_no,
                turn_number=turn_no,
                role="assistant",
                content=text,
                question_id=str(question.question_id),
                is_opening=is_opening,
                generation_id=generation_id,
            )
        )
        return message, event_id

    def _mark_generation_failed(
        self,
        *,
        message_id: str,
        generation_id: str,
        exc: Exception,
    ) -> None:
        """保存失败快照并发布可重试错误事件。"""
        logger.exception(
            "[Dialog Agent] 真实模型调用失败: session=%s, error=%s",
            self.session_id,
            type(exc).__name__,
        )
        error_event_id = self.publisher.publish(
            AgentErrorEvent(
                session_id=self.session_id,
                task_id=self.task_id,
                message_id=message_id,
                agent_name="dialog_agent",
                error_code="MODEL_CALL_FAILED",
                message="AI 模型调用失败，后台正在重试",
                retrying=True,
                generation_id=generation_id,
            )
        )
        self.output_store.fail(
            session_id=self.session_id,
            message_id=message_id,
            error_code="MODEL_CALL_FAILED",
            error_message=str(exc),
            last_event_id=error_event_id,
        )

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

    def _load_patient_message(self, message_no: str) -> InteractionMessage:
        """读取本会话指定患者答案。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            message = db.scalar(
                select(InteractionMessage).where(
                    InteractionMessage.interaction_session_id
                    == self.interaction_session_id,
                    InteractionMessage.message_no == message_no,
                    InteractionMessage.role_type.in_(["患者", "家属", "user"]),
                    InteractionMessage.deleted == 0,
                )
            )
            if message is None:
                raise RuntimeError(f"患者答案不存在: {message_no}")
            db.expunge(message)
            return message

    def _find_ai_message(self, *, turn_no: int) -> InteractionMessage | None:
        """查询指定轮次已经持久化的 AI 问句。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            message = db.scalar(
                select(InteractionMessage)
                .where(
                    InteractionMessage.interaction_session_id
                    == self.interaction_session_id,
                    InteractionMessage.turn_no == turn_no,
                    InteractionMessage.role_type.in_(["AI", "assistant"]),
                    InteractionMessage.deleted == 0,
                )
                .order_by(InteractionMessage.id.desc())
            )
            if message is not None:
                db.expunge(message)
            return message

    def _resolve_current_question_index(
        self,
        patient_message: InteractionMessage,
        questions: list[QuestionTask],
    ) -> int:
        """根据患者答案同轮 AI 问句恢复 Task-todo 位置。"""
        asked = self._find_ai_message(turn_no=patient_message.turn_no)
        if asked is None:
            raise RuntimeError(
                f"患者答案缺少对应 AI 问句: turn={patient_message.turn_no}"
            )
        return self._question_index(asked.related_question_id, questions)

    @staticmethod
    def _question_index(
        question_id: int | None,
        questions: list[QuestionTask],
    ) -> int:
        """将数据库问题主键映射到 Task-todo 下标。"""
        for index, question in enumerate(questions):
            if question.question_id == question_id:
                return index
        raise RuntimeError(f"AI 问句未关联有效量表问题: {question_id}")

    async def _build_agent(
        self,
        *,
        questions: list[QuestionTask],
        turn_no: int,
        patient_answer: str,
        next_question: QuestionTask,
        text_delta_sink: Callable[[str, dict[str, Any]], Awaitable[None]],
    ):
        """按 PostgreSQL 历史重建单轮文本 Agent。"""
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
            text_delta_sink=text_delta_sink,
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
                "如果 Schedule 约束要求追问，先完成追问；否则必须询问以下目标题目，"
                "不得回答患者，不得一次询问多题："
                f"{next_question.patient_text or next_question.question_name}"
            )
        )
        return agent

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
        logger.info("AI 问诊完成: session=%s turns=%s", self.session_id, turn_counter)

    def _restore_state(self) -> dict[str, Any] | None:
        """恢复 Redis 运行状态。"""
        state = self.redis.get(self.state_key)
        return state if isinstance(state, dict) else None

    def _rebuild_state_from_history(
        self,
        questions: list[QuestionTask],
    ) -> dict[str, Any]:
        """Redis 状态缺失时从 PostgreSQL 历史恢复题目位置和轮次。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            latest = db.scalar(
                select(InteractionMessage)
                .where(
                    InteractionMessage.interaction_session_id
                    == self.interaction_session_id,
                    InteractionMessage.role_type.in_(["AI", "assistant"]),
                    InteractionMessage.deleted == 0,
                )
                .order_by(
                    InteractionMessage.turn_no.desc(),
                    InteractionMessage.id.desc(),
                )
            )
            if latest is None:
                return {
                    "current_question_index": 0,
                    "turn_counter": 0,
                    "last_event_id": "0-0",
                    "processed_message_ids": [],
                }
            current_index = self._question_index(latest.related_question_id, questions)
            patient_message_ids = list(
                db.scalars(
                    select(InteractionMessage.message_no).where(
                        InteractionMessage.interaction_session_id
                        == self.interaction_session_id,
                        InteractionMessage.role_type.in_(["患者", "家属", "user"]),
                        InteractionMessage.turn_no < latest.turn_no,
                        InteractionMessage.deleted == 0,
                    )
                ).all()
            )
            return {
                "current_question_index": current_index,
                "turn_counter": latest.turn_no,
                "last_event_id": "0-0",
                "processed_message_ids": patient_message_ids[-100:],
            }

    def _save_state(
        self,
        *,
        current_question_index: int,
        turn_counter: int,
        last_event_id: str,
        processed_message_ids: list[str],
    ) -> None:
        """保存可恢复的单轮运行状态。"""
        saved = self.redis.set(
            self.state_key,
            {
                "current_question_index": current_question_index,
                "turn_counter": turn_counter,
                "last_event_id": last_event_id,
                "processed_message_ids": processed_message_ids[-100:],
            },
            ex=self.state_ttl,
        )
        if not saved:
            raise RuntimeError(f"Dialog Agent 状态保存失败: {self.state_key}")

    def _ensure_completed_snapshot(
        self,
        *,
        message: InteractionMessage,
        question_id: int | None,
        is_opening: bool,
    ) -> None:
        """重试时由 PostgreSQL 完整消息恢复 Redis 快照。"""
        generation_id, stable_message_id = self._generation_ids(
            "opening" if is_opening else self._source_id_for_turn(message.turn_no)
        )
        snapshot = self.output_store.get(self.session_id, message.message_no)
        if snapshot is not None and snapshot.get("status") == "completed":
            return
        self.output_store.start(
            session_id=self.session_id,
            task_id=self.task_id,
            message_id=message.message_no or stable_message_id,
            generation_id=generation_id,
            turn_number=message.turn_no,
            question_id=question_id,
        )
        event_id = self.publisher.publish(
            DialogMessageEvent(
                session_id=self.session_id,
                task_id=self.task_id,
                message_id=message.message_no,
                turn_number=message.turn_no,
                content=str(message.content_text or ""),
                question_id=str(question_id) if question_id is not None else None,
                is_opening=is_opening,
                generation_id=generation_id,
            )
        )
        self.output_store.complete(
            session_id=self.session_id,
            message_id=message.message_no,
            content=str(message.content_text or ""),
            last_event_id=event_id,
        )

    def _source_id_for_turn(self, turn_no: int) -> str:
        """查询产生指定 AI 轮次的上一轮患者消息编号。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            message_no = db.scalar(
                select(InteractionMessage.message_no)
                .where(
                    InteractionMessage.interaction_session_id
                    == self.interaction_session_id,
                    InteractionMessage.turn_no == turn_no - 1,
                    InteractionMessage.role_type.in_(["患者", "家属", "user"]),
                    InteractionMessage.deleted == 0,
                )
                .order_by(InteractionMessage.id.desc())
            )
            return str(message_no or f"turn-{turn_no}")

    def _generation_ids(self, work_id: str) -> tuple[str, str]:
        """按会话和工作单元生成稳定的生成编号与消息编号。"""
        stable = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"medical-evaluate:{self.session_id}:{work_id}",
        ).hex.upper()
        return f"GEN-{stable[:20]}", f"MSG-AI-{stable[:24]}"
