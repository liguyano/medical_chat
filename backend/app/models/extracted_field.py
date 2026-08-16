"""字段抽取结果模型
作用：定义字段抽取结果表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, TIMESTAMP, Float, Boolean, CheckConstraint, Index, ForeignKey, UniqueConstraint
from app.models.base import Base


class ExtractedField(Base):
    """字段抽取结果表
    作用：记录从对话中抽取的结构化字段
    """
    __tablename__ = "extracted_fields"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("dialog_sessions.session_id", ondelete="CASCADE"), nullable=False)
    form_id = Column(String(50), nullable=False, comment="量表ID")
    field_key = Column(String(100), nullable=False, comment="字段键名")
    field_value = Column(Text, nullable=True, comment="字段值")
    confidence = Column(Float, CheckConstraint("confidence >= 0 AND confidence <= 1"), nullable=True, comment="抽取置信度")
    source_message_id = Column(String(64), ForeignKey("dialog_messages.message_id", ondelete="SET NULL"), nullable=True)
    extraction_time = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    is_confirmed = Column(Boolean, default=False, comment="是否已人工确认")
    confirmed_by = Column(BigInteger, nullable=True, comment="确认人ID")
    confirmed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "form_id", "field_key", name="uk_extracted_fields"),
        Index("idx_extracted_fields_session_id", "session_id"),
        Index("idx_extracted_fields_form_id", "form_id"),
        Index("idx_extracted_fields_is_confirmed", "is_confirmed"),
        Index("idx_extracted_fields_confidence", "confidence", postgresql_ops={"confidence": "DESC"}),
    )
