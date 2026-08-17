"""AI 对话与交互域 ORM 模型
作用：定义交互会话、消息、事件、规则、话术和逐轮反馈。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BusinessBaseMixin


class InteractionSession(BusinessBaseMixin, Base):
    """AI 与患者、家属或护士的一次连续交互。"""

    __tablename__ = "interaction_session"

    session_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("care_task.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient.id", ondelete="RESTRICT"),
        nullable=False,
    )
    encounter_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient_encounter.id", ondelete="RESTRICT"),
        nullable=False,
    )
    participant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    interaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    script_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handoff_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_interaction_session_task", "task_id", "deleted"),
        Index("idx_interaction_session_patient", "patient_id", "deleted"),
        Index("idx_interaction_session_status", "session_status", "deleted"),
    )


class InteractionMessage(BusinessBaseMixin, Base):
    """对话消息历史，保留患者原话和 AI 输出。"""

    __tablename__ = "interaction_message"

    interaction_session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interaction_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    parent_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("interaction_message.id", ondelete="SET NULL"),
        nullable=True,
    )
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cicare_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    asr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_question_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("assessment_question.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 知情同意与宣教域属于批次 B；先保留可追溯 ID，后续迁移再补外键。
    related_clause_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    related_material_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_interaction_message_session_turn", "interaction_session_id", "turn_no"),
        Index("idx_interaction_message_occurred", "occurred_at"),
        Index("idx_interaction_message_question", "related_question_id"),
    )


class InteractionRule(BusinessBaseMixin, Base):
    """交互触发规则。"""

    __tablename__ = "interaction_rule"

    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trigger_condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (Index("idx_interaction_rule_status_priority", "status", "priority"),)


class InteractionEvent(BusinessBaseMixin, Base):
    """对话中发生的业务事件。"""

    __tablename__ = "interaction_event"

    interaction_session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interaction_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("interaction_message.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("interaction_rule.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    handled_status: Mapped[str] = mapped_column(String(32), nullable=False)
    handled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_interaction_event_session", "interaction_session_id", "deleted"),
        Index("idx_interaction_event_status", "handled_status", "deleted"),
    )


class DialogueScript(BusinessBaseMixin, Base):
    """CICARE、追问、宣教和确认话术。"""

    __tablename__ = "dialogue_script"

    script_code: Mapped[str] = mapped_column(String(64), nullable=False)
    script_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cicare_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    audience_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("script_code", "version_code", "language_code", name="uq_script_version_language"),
        Index("idx_dialogue_script_type", "script_type", "deleted"),
    )


class InteractionMessageFeedback(BusinessBaseMixin, Base):
    """护士对单条 AI 消息的 RLHF 逐轮标注。"""

    __tablename__ = "interaction_message_feedback"

    interaction_session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interaction_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    interaction_message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interaction_message.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "interaction_message_id",
            "reviewer_id",
            name="uq_message_feedback_reviewer",
        ),
        Index("idx_message_feedback_session", "interaction_session_id", "turn_no"),
        Index("idx_message_feedback_type", "feedback_type"),
    )
