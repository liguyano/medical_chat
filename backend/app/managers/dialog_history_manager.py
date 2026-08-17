"""对话历史管理器
作用：基于 interaction_session / interaction_message 保存、查询和格式化对话消息。
"""
import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import InteractionMessage, InteractionSession
from app.models import base as model_base

logger = logging.getLogger(__name__)


class DialogHistoryManager:
    """对话历史管理器
    作用：提供消息级 CRUD、分页查询和 LangChain 消息格式转换。
    """

    def __init__(self, session_factory: sessionmaker[Session] | None = None):
        """初始化管理器
        Args:
            - session_factory: 可选会话工厂；为空时使用 init_db() 初始化的全局工厂
        """
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    @staticmethod
    def _get_session_id(db: Session, session_no: str) -> int:
        """按业务会话编号解析主键。"""
        session_id = db.scalar(
            select(InteractionSession.id).where(
                InteractionSession.session_no == session_no,
                InteractionSession.deleted == 0,
            )
        )
        if session_id is None:
            raise LookupError(f"交互会话不存在: {session_no}")
        return session_id

    async def save_message(
        self,
        session_no: str,
        *,
        turn_no: int,
        role_type: str,
        message_type: str,
        content_text: str | None = None,
        message_no: str | None = None,
        parent_message_id: int | None = None,
        cicare_stage: str | None = None,
        intent_type: str | None = None,
        audio_url: str | None = None,
        asr_text: str | None = None,
        tts_text: str | None = None,
        related_question_id: int | None = None,
        related_clause_id: int | None = None,
        related_material_id: int | None = None,
        occurred_at: datetime | None = None,
        creator: str | None = None,
    ) -> InteractionMessage:
        """保存一条交互消息。"""
        with self._new_session() as db:
            try:
                interaction_session_id = self._get_session_id(db, session_no)
                message = InteractionMessage(
                    interaction_session_id=interaction_session_id,
                    message_no=message_no or str(uuid4()),
                    parent_message_id=parent_message_id,
                    turn_no=turn_no,
                    role_type=role_type,
                    message_type=message_type,
                    cicare_stage=cicare_stage,
                    intent_type=intent_type,
                    content_text=content_text,
                    audio_url=audio_url,
                    asr_text=asr_text,
                    tts_text=tts_text,
                    related_question_id=related_question_id,
                    related_clause_id=related_clause_id,
                    related_material_id=related_material_id,
                    occurred_at=occurred_at or datetime.now(UTC),
                    creator=creator,
                    updator=creator,
                )
                db.add(message)
                db.commit()
                db.refresh(message)
                logger.info("对话消息保存成功: session=%s message=%s", session_no, message.message_no)
                return message
            except Exception:
                db.rollback()
                logger.exception("保存对话消息失败: session=%s turn=%s", session_no, turn_no)
                raise

    async def get_dialog_history(
        self,
        session_no: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[InteractionMessage]:
        """按发生时间正序分页查询对话历史。"""
        with self._new_session() as db:
            session_id = self._get_session_id(db, session_no)
            statement = (
                select(InteractionMessage)
                .where(
                    InteractionMessage.interaction_session_id == session_id,
                    InteractionMessage.deleted == 0,
                )
                .order_by(
                    InteractionMessage.turn_no.asc(),
                    InteractionMessage.occurred_at.asc(),
                    InteractionMessage.id.asc(),
                )
                .offset(offset)
            )
            if limit is not None:
                statement = statement.limit(limit)
            return list(db.scalars(statement).all())

    async def get_latest_messages(
        self,
        session_no: str,
        *,
        count: int = 10,
    ) -> list[InteractionMessage]:
        """获取最近 N 条消息，并按时间正序返回。"""
        if count <= 0:
            return []
        with self._new_session() as db:
            session_id = self._get_session_id(db, session_no)
            messages = list(
                db.scalars(
                    select(InteractionMessage)
                    .where(
                        InteractionMessage.interaction_session_id == session_id,
                        InteractionMessage.deleted == 0,
                    )
                    .order_by(
                        InteractionMessage.occurred_at.desc(),
                        InteractionMessage.id.desc(),
                    )
                    .limit(count)
                ).all()
            )
            messages.reverse()
            return messages

    @staticmethod
    def format_for_langchain(history: list[InteractionMessage]) -> list[dict[str, str]]:
        """转换为 LangChain 消息字典格式。"""
        role_map = {
            "AI": "assistant",
            "assistant": "assistant",
            "患者": "user",
            "家属": "user",
            "user": "user",
            "护士": "user",
            "系统": "system",
            "system": "system",
        }
        return [
            {
                "role": role_map.get(message.role_type, message.role_type),
                "content": message.content_text or message.asr_text or "",
            }
            for message in history
            if message.content_text or message.asr_text
        ]

    async def count_messages(self, session_no: str) -> int:
        """统计会话有效消息数量。"""
        with self._new_session() as db:
            session_id = self._get_session_id(db, session_no)
            return int(
                db.scalar(
                    select(func.count(InteractionMessage.id)).where(
                        InteractionMessage.interaction_session_id == session_id,
                        InteractionMessage.deleted == 0,
                    )
                )
                or 0
            )

    async def delete_session_history(self, session_no: str, *, updator: str | None = None) -> int:
        """逻辑删除会话历史，禁止物理删除临床数据。"""
        with self._new_session() as db:
            try:
                session_id = self._get_session_id(db, session_no)
                result = db.execute(
                    update(InteractionMessage)
                    .where(
                        InteractionMessage.interaction_session_id == session_id,
                        InteractionMessage.deleted == 0,
                    )
                    .values(deleted=1, updator=updator, update_time=datetime.now(UTC))
                )
                db.commit()
                return int(result.rowcount or 0)
            except Exception:
                db.rollback()
                logger.exception("逻辑删除对话历史失败: session=%s", session_no)
                raise

    async def get_full_context(self, session_no: str, max_characters: int = 8000) -> str:
        """生成用于模型推理的文本上下文。"""
        history = await self.get_dialog_history(session_no)
        parts: list[str] = []
        used = 0
        role_labels = {
            "AI": "AI",
            "assistant": "AI",
            "患者": "患者",
            "家属": "家属",
            "user": "患者",
            "护士": "护士",
            "系统": "系统",
            "system": "系统",
        }
        for message in reversed(history):
            content = message.content_text or message.asr_text
            if not content:
                continue
            part = f"{role_labels.get(message.role_type, message.role_type)}: {content}\n"
            if used + len(part) > max_characters:
                break
            parts.insert(0, part)
            used += len(part)
        return "".join(parts)
