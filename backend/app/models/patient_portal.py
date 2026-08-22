"""患者门户补充域 ORM 模型。

作用：承载患者端身份入口、住院助手、通知/病区指南、知情同意快照和
播报播放进度。字段严格对应两份患者端数据库业务设计文档；运行态连接、
限流和一次性令牌仍保存在 Redis。
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


class PatientNotification(BusinessBaseMixin, Base):
    """患者通知。"""

    __tablename__ = "patient_notification"

    notification_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("patient_encounter.id", ondelete="SET NULL"), nullable=True
    )
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_patient_notification_owner", "patient_id", "encounter_id", "deleted"),
        Index("idx_patient_notification_unread", "patient_id", "read_at", "deleted"),
    )


class WardGuide(BusinessBaseMixin, Base):
    """病区/科室可见的住院生活指南条目。"""

    __tablename__ = "ward_guide"

    guide_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    department_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ward_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="住院生活")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")

    __table_args__ = (
        Index("idx_ward_guide_scope", "department_code", "ward_name", "status", "deleted"),
    )


class PatientAssistantSession(BusinessBaseMixin, Base):
    """独立于护理评估的住院助手会话。"""

    __tablename__ = "patient_assistant_session"

    session_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient_encounter.id", ondelete="CASCADE"), nullable=False
    )
    channel_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    session_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handoff_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handoff_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_patient_assistant_owner", "patient_id", "encounter_id", "deleted"),
    )


class PatientAssistantMessage(BusinessBaseMixin, Base):
    """住院助手问答消息。"""

    __tablename__ = "patient_assistant_message"

    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patient_assistant_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_guide_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ward_guide.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_patient_assistant_message_session", "session_id", "occurred_at"),)


class ConsentDocument(BusinessBaseMixin, Base):
    """知情同意文档主档。"""

    __tablename__ = "consent_document"

    consent_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    consent_name: Mapped[str] = mapped_column(String(160), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class ConsentDocumentVersion(BusinessBaseMixin, Base):
    """知情同意文档发布版本及完整原文快照。"""

    __tablename__ = "consent_document_version"

    consent_document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_document.id", ondelete="CASCADE"), nullable=False
    )
    version_code: Mapped[str] = mapped_column(String(64), nullable=False)
    publish_status: Mapped[str] = mapped_column(String(32), nullable=False, default="published")
    effective_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint(
            "consent_document_id", "version_code", name="uq_consent_document_version"
        ),
        Index("idx_consent_version_publish", "consent_document_id", "publish_status", "deleted"),
    )


class ConsentClause(BusinessBaseMixin, Base):
    """可逐条播报和确认的知情同意条款。"""

    __tablename__ = "consent_clause"

    consent_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("consent_document_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    clause_code: Mapped[str] = mapped_column(String(64), nullable=False)
    clause_title: Mapped[str] = mapped_column(String(160), nullable=False)
    original_content: Mapped[str] = mapped_column(Text, nullable=False)
    patient_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    importance_level: Mapped[str] = mapped_column(String(32), nullable=False, default="一般")
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    teachback_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("consent_version_id", "clause_code", name="uq_consent_clause_code"),
        Index("idx_consent_clause_sort", "consent_version_id", "sort_no", "deleted"),
    )


class ConsentRecord(BusinessBaseMixin, Base):
    """患者一次知情同意宣讲和确认记录。"""

    __tablename__ = "consent_record"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("care_task.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient.id", ondelete="RESTRICT"), nullable=False
    )
    encounter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient_encounter.id", ondelete="RESTRICT"), nullable=False
    )
    consent_document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_document.id", ondelete="RESTRICT"), nullable=False
    )
    consent_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_document_version.id", ondelete="RESTRICT"), nullable=False
    )
    interaction_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("interaction_session.id", ondelete="SET NULL"), nullable=True
    )
    participant_type: Mapped[str] = mapped_column(String(32), nullable=False, default="patient")
    record_status: Mapped[str] = mapped_column(String(32), nullable=False, default="进行中")
    patient_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nurse_confirmed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint("task_id", "consent_version_id", name="uq_consent_record_task_version"),
        Index("idx_consent_record_patient", "patient_id", "encounter_id", "deleted"),
    )


class ConsentClauseRecord(BusinessBaseMixin, Base):
    """患者对单条知情同意条款的确认。"""

    __tablename__ = "consent_clause_record"

    consent_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False
    )
    clause_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_clause.id", ondelete="RESTRICT"), nullable=False
    )
    patient_reply_message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("interaction_message.id", ondelete="SET NULL"), nullable=True
    )
    confirmation_result: Mapped[str] = mapped_column(String(32), nullable=False)
    patient_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    need_nurse_explain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("consent_record_id", "clause_id", name="uq_consent_clause_record"),
    )


class ConsentRecordItem(BusinessBaseMixin, Base):
    """知情同意中的费用/项目确认项。"""

    __tablename__ = "consent_record_item"

    consent_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False
    )
    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    item_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    patient_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConsentParticipant(BusinessBaseMixin, Base):
    """知情同意患者/家属参与人快照。"""

    __tablename__ = "consent_participant"

    consent_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False
    )
    participant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    participant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_to_patient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id_card_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_phone_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsentAuthorization(BusinessBaseMixin, Base):
    """家属代签授权记录。"""

    __tablename__ = "consent_authorization"

    consent_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False
    )
    principal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_to_patient: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorization_file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConsentSignature(BusinessBaseMixin, Base):
    """知情同意电子/手写签名存证。"""

    __tablename__ = "consent_signature"

    consent_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("consent_participant.id", ondelete="SET NULL"), nullable=True
    )
    signer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    signer_name_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    signature_method: Mapped[str] = mapped_column(String(32), nullable=False)
    signature_file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    signed_content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_consent_signature_record", "consent_record_id", "deleted"),)


class ContentDeliverySession(BusinessBaseMixin, Base):
    """知情同意/宣教通用播报会话。"""

    __tablename__ = "content_delivery_session"

    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient.id", ondelete="CASCADE"), nullable=False
    )
    encounter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("patient_encounter.id", ondelete="CASCADE"), nullable=False
    )
    business_type: Mapped[str] = mapped_column(String(32), nullable=False)
    business_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_type: Mapped[str] = mapped_column(String(16), nullable=False, default="voice")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentDeliveryItem(BusinessBaseMixin, Base):
    """实际播报内容快照和当前播放进度。"""

    __tablename__ = "content_delivery_item"

    delivery_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_delivery_session.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    patient_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audio_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    playback_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    patient_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContentPlaybackEvent(BusinessBaseMixin, Base):
    """播报开始、暂停、继续、完成、重播等操作事件。"""

    __tablename__ = "content_playback_event"

    delivery_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_delivery_item.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_invocation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "delivery_item_id",
            "client_invocation_id",
            name="uq_content_playback_invocation",
        ),
    )
