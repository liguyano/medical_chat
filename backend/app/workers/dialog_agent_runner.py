"""Dialog Agent 单轮运行器
作用：按需创建文本 Agent，生成首问或消费一条患者答案，并在任务结束后释放实例。
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from medagent.agents.factory import create_dialog_agent
from medagent.agents.service_agent.dialog_agent.agent import GENERIC_ERROR_MESSAGE
from medagent.agents.service_agent.dialog_agent.engine import TextChatEngine
from medagent.agents.service_agent.schedule_agent.models import QuestionTask
from sqlalchemy import func, select

from app.managers.assessment_loader import AssessmentQuestionLoader
from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import base as model_base
from app.models.assessment_execution import AssessmentAnswer, AssessmentSubmission
from app.models.assessment_template import AssessmentQuestion
from app.models.interaction import InteractionMessage, InteractionSession
from app.schemas.events import (
    AgentErrorEvent,
    AssistantMessageStartedEvent,
    DialogMessageEvent,
    DialogTextEvent,
    SessionEndEvent,
)
from app.services.assessment_progress_service import (
    complete_assessment_session,
    refresh_assessment_progress,
    valid_assessment_answer_condition,
)
from app.utils.redis_client import RedisClient
from app.workers.dialog_output_store import DialogOutputStore
from app.workers.event_publisher import DialogEventPublisher
from app.workers.schedule_task_store import ScheduleTaskStore
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
        finalize: bool = False,
    ) -> dict[str, Any]:
        """生成首问或处理一条患者答案
        作用：每次 Celery 调用只处理一个工作单元，不在任务内长驻等待 Redis Stream。
        Args:
            - source_message_id: 患者答案消息编号；为空时生成首问。
            - source_event_id: 患者答案在 Redis Stream 中的事件游标。
        Return:
            - 当前工作单元的执行状态。
        """
        task_store = ScheduleTaskStore(self.redis, ttl=self.state_ttl)
        plan = task_store.get_plan(self.session_id)
        questions = (
            plan.tasks
            if plan is not None and plan.tasks
            else await self.loader.load_questions_by_scale_codes(self.scale_codes)
        )
        if not questions:
            return {"status": "failed", "reason": "no_questions_loaded"}
        self._load_session_context()

        work_id = "completion" if finalize else source_message_id or "opening"
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
            if finalize:
                return await self._run_completion()
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

    async def _run_completion(self) -> dict[str, Any]:
        """在结构化进度完整后生成 CICARE Exit 并提交任务。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            progress = refresh_assessment_progress(db, self.session_id)
            if not progress.completed:
                return {
                    "status": "not_ready",
                    "session_id": self.session_id,
                    "progress_current": progress.current,
                    "progress_total": progress.total,
                }
            turn_no = int(
                db.scalar(
                    select(func.max(InteractionMessage.turn_no)).where(
                        InteractionMessage.interaction_session_id
                        == self.interaction_session_id,
                        InteractionMessage.deleted == 0,
                    )
                )
                or 0
            ) + 1

        generation_id, message_id = self._generation_ids("completion")
        existing = self._find_message_by_no(message_id)
        started_event_id: str | None = None
        closing_text = str(existing.content_text or "") if existing is not None else ""

        async def on_delta(text_chunk: str) -> None:
            self._publish_text_delta(
                generation_id=generation_id,
                message_id=message_id,
                turn_number=turn_no,
                question_id=None,
                text_chunk=text_chunk,
            )

        try:
            if existing is None:
                started_event_id = self._start_generation(
                    generation_id=generation_id,
                    message_id=message_id,
                    turn_number=turn_no,
                    question_id=None,
                )
                closing_text = await self._generate_completion_message(
                    on_delta=on_delta
                )
                message = await self.history.save_message(
                    self.session_id,
                    message_no=message_id,
                    turn_no=turn_no,
                    role_type="AI",
                    message_type="文本",
                    content_text=closing_text,
                    intent_type="确认",
                    related_question_id=None,
                    creator="dialog_agent",
                )
            else:
                message = existing
                turn_no = message.turn_no

            with model_base.SessionLocal() as db:
                completed_progress = complete_assessment_session(db, self.session_id)
            if not completed_progress.completed:
                raise RuntimeError("CICARE 结束语已生成，但结构化评估进度不再完整")

            completed_event_id = self.publisher.publish(
                DialogMessageEvent(
                    session_id=self.session_id,
                    task_id=self.task_id,
                    message_id=message.message_no,
                    turn_number=turn_no,
                    role="assistant",
                    content=closing_text,
                    question_id=None,
                    is_opening=False,
                    generation_id=generation_id,
                )
            )
            self.output_store.complete(
                session_id=self.session_id,
                message_id=message_id,
                content=closing_text,
                last_event_id=completed_event_id or started_event_id,
            )
            self.publisher.publish(
                SessionEndEvent(
                    session_id=self.session_id,
                    task_id=self.task_id,
                    message_id=message_id,
                    end_reason="completed",
                    total_turns=turn_no,
                    duration_seconds=0,
                )
            )
            return {
                "status": (
                    "already_completed" if existing is not None else "completed"
                ),
                "session_id": self.session_id,
                "message_id": message_id,
            }
        except Exception as exc:
            self._mark_generation_failed(
                message_id=message_id,
                generation_id=generation_id,
                exc=exc,
            )
            raise

    async def _generate_completion_message(
        self,
        *,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """生成符合 CICARE Exit 的自然结束语。"""
        messages = [
            SystemMessage(
                content=(
                    "你是住院病区的 AI 护理助手。系统已经确认全部必填护理评估信息完整。"
                    "请按 CICARE Exit 用两到三句自然中文结束：感谢患者配合，"
                    "说明护士会复核记录并告知下一步护理安排，提醒仍有不适可及时呼叫医护人员。"
                    "不要重复量表内容，不要夸大诊断，不要使用客服式套话。"
                )
            ),
            HumanMessage(
                content=f"患者称呼参考：{self.patient_info.get('name', '患者')}",
            ),
        ]
        chunks: list[str] = []
        stream = getattr(self.model, "astream", None)
        if callable(stream):
            async for chunk in stream(messages):
                text = self._message_content(chunk)
                if text:
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
        result = "".join(chunks).strip()
        if not result:
            raise RuntimeError("Dialog Agent 未返回 CICARE 结束语")
        return result

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
                "content": existing.content_text or "",
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
                "content": opening_text,
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

        next_question, plan_exhausted = self._select_next_question(
            current_question=questions[current_index],
            questions=questions,
        )
        next_index = self._question_index(next_question.question_id, questions)
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
                plan_exhausted=plan_exhausted,
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
                    "你是住院病区的 AI 护理助手，正在按 CICARE 开始护理评估。"
                    "开场需要自然完成：使用患者称呼、简短慰问、自我介绍、说明职责和评估配合方式。"
                    "称呼可能不合适时请允许患者纠正，但不要连续抛出身份核实问题。"
                    "随后自然过渡到一个护理评估问题。整段应像真人护士交流，"
                    "不要念量表名称，不要使用“您的某某情况是怎样的”这类问卷句式，"
                    "不要一次询问多个评估主题。"
                )
            ),
            HumanMessage(
                content=(
                    f"患者姓名：{self.patient_info.get('name', '患者')}。"
                    f"当前住院诊断快照（仅供内部理解，不得向患者宣告）："
                    f"{json.dumps(self.patient_info.get('diagnosis_snapshot') or {}, ensure_ascii=False)}。"
                    f"第一项需要了解的护理事实：{question.question_name}。"
                    f"量表参考表达：{target_text}"
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
        question_id: int | None,
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
                question_id=str(question_id) if question_id is not None else None,
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
        question_id: int | None,
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
                question_id=str(question_id) if question_id is not None else None,
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
        if is_opening:
            self._activate_session()
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

    def _activate_session(self) -> None:
        """首问持久化后允许患者开始输入。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            session = db.get(InteractionSession, self.interaction_session_id)
            if session is not None and session.session_status == "pending":
                session.session_status = "active"
                session.updator = "dialog_agent"
                db.commit()

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

    def _find_message_by_no(self, message_no: str) -> InteractionMessage | None:
        """按稳定消息编号查询本会话消息。"""
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            message = db.scalar(
                select(InteractionMessage).where(
                    InteractionMessage.interaction_session_id
                    == self.interaction_session_id,
                    InteractionMessage.message_no == message_no,
                    InteractionMessage.deleted == 0,
                )
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

    def _select_next_question(
        self,
        *,
        current_question: QuestionTask,
        questions: list[QuestionTask],
    ) -> tuple[QuestionTask, bool]:
        """选择下一个尚未覆盖的 Task-todo 项。
        作用：优先跳过已持久化答案和已问过的同编码问题；当计划已经问完但
        Extraction 尚未确认完整时，返回当前问题作为核对上下文，不触发完成。
        """
        if model_base.SessionLocal is None:
            raise RuntimeError("数据库未初始化")
        with model_base.SessionLocal() as db:
            answered_codes = set(
                db.scalars(
                    select(AssessmentQuestion.question_code)
                    .join(
                        AssessmentAnswer,
                        AssessmentAnswer.question_id == AssessmentQuestion.id,
                    )
                    .join(
                        AssessmentSubmission,
                        AssessmentSubmission.id == AssessmentAnswer.submission_id,
                    )
                    .where(
                        AssessmentSubmission.interaction_session_id
                        == self.interaction_session_id,
                        AssessmentSubmission.deleted == 0,
                        AssessmentAnswer.deleted == 0,
                        valid_assessment_answer_condition(),
                    )
                ).all()
            )
            asked_codes = set(
                db.scalars(
                    select(AssessmentQuestion.question_code)
                    .join(
                        InteractionMessage,
                        InteractionMessage.related_question_id == AssessmentQuestion.id,
                    )
                    .where(
                        InteractionMessage.interaction_session_id
                        == self.interaction_session_id,
                        InteractionMessage.role_type.in_(["AI", "assistant"]),
                        InteractionMessage.deleted == 0,
                    )
                ).all()
            )
        covered_codes = answered_codes | asked_codes | {current_question.question_code}
        for question in questions:
            if question.question_code not in covered_codes:
                return question, False
        return current_question, True

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
        plan_exhausted: bool,
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
        guidance = ScheduleTaskStore(self.redis, ttl=self.state_ttl).get_guidance(
            self.session_id
        )
        if plan_exhausted:
            turn_instruction = (
                "Task-todo 中的主题都已经问过，但后台结构化抽取尚未确认全部完成。"
                "先自然回应患者刚才的内容；不要宣布评估完成，不要重复照抄刚才的问题。"
                "请邀请患者补充仍有的不适、担心、需要解决的问题或需要的帮助。"
            )
        else:
            turn_instruction = (
                "先用一小句自然回应患者刚才的内容，再顺畅过渡到一个下一问。"
                "不得生硬复述字段名，不得一次询问多个主题。"
                f"本轮要收集的护理事实是：{next_question.question_name}；"
                f"量表参考表达：{next_question.patient_text or next_question.question_name}。"
            )
        schedule_prompt = str(guidance.get("constraint_prompt") or "").strip()
        await agent.engine.update_session(
            instructions=(
                f"{turn_instruction}"
                "患者提出问题时先简短回答；不知道具体病区设施位置时，应说明需向本病区护士确认，"
                "不得编造开水房、茶水室或微波炉的位置。"
                "药物过敏、吸烟饮酒、手术等特征应按工具规则追问或宣教。"
                + (f" Schedule Agent 最新引导：{schedule_prompt}" if schedule_prompt else "")
            )
        )
        return agent

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
