"""对话消息模型
作用：定义对话消息表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, TIMESTAMP, Integer, CheckConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class DialogMessage(Base):
    """对话消息表
    作用：记录所有对话历史
    """
    __tablename__ = "dialog_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(String(64), unique=True, nullable=False, comment="消息UUID")
    session_id = Column(String(64), ForeignKey("dialog_sessions.session_id", ondelete="CASCADE"), nullable=False)
    turn_number = Column(Integer, nullable=False, comment="对话轮次")
    role = Column(String(20), nullable=False, comment="角色")
    content = Column(Text, nullable=False, comment="消息内容")
    content_type = Column(String(20), default="text", comment="内容类型")
    tool_calls = Column(JSONB, nullable=True, comment="工具调用记录")
    audio_url = Column(String(255), nullable=True, comment="语音文件URL")
    message_metadata = Column(JSONB, nullable=True, comment="额外元数据")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="chk_role"
        ),
        CheckConstraint(
            "content_type IN ('text', 'audio', 'tool_call', 'tool_result')",
            name="chk_content_type"
        ),
        Index("idx_dialog_messages_session_id", "session_id"),
        Index("idx_dialog_messages_turn_number", "session_id", "turn_number"),
        Index("idx_dialog_messages_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
        Index("idx_dialog_messages_role", "role"),
    )
