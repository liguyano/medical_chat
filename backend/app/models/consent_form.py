"""知情同意书签署模型
作用：定义知情同意书签署表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, Boolean, TIMESTAMP, Index, ForeignKey
from app.models.base import Base


class ConsentForm(Base):
    """知情同意书签署表
    作用：记录知情同意书签署情况
    """
    __tablename__ = "consent_forms"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("dialog_sessions.session_id", ondelete="CASCADE"), nullable=False)
    message_id = Column(String(64), ForeignKey("dialog_messages.message_id", ondelete="SET NULL"), nullable=True)
    form_type = Column(String(50), nullable=False, comment="表单类型")
    form_content = Column(Text, nullable=False, comment="知情同意书内容")
    is_signed = Column(Boolean, default=False, comment="是否已签署")
    signature_data = Column(Text, nullable=True, comment="签名图片base64或URL")
    signed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index("idx_consent_forms_session_id", "session_id"),
        Index("idx_consent_forms_form_type", "form_type"),
        Index("idx_consent_forms_is_signed", "is_signed"),
    )
