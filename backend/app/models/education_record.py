"""宣教记录模型
作用：定义宣教记录表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Integer, Boolean, TIMESTAMP, CheckConstraint, Index, ForeignKey
from app.models.base import Base


class EducationRecord(Base):
    """宣教记录表
    作用：记录分级宣教执行情况
    """
    __tablename__ = "education_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("dialog_sessions.session_id", ondelete="CASCADE"), nullable=False)
    message_id = Column(String(64), ForeignKey("dialog_messages.message_id", ondelete="SET NULL"), nullable=True)
    education_type = Column(String(50), nullable=False, comment="宣教类别")
    material_id = Column(String(50), nullable=False, comment="宣教材料ID")
    level = Column(Integer, CheckConstraint("level >= 1 AND level <= 3"), nullable=True, comment="宣教级别")
    is_completed = Column(Boolean, default=False, comment="是否完成宣读")
    started_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index("idx_education_records_session_id", "session_id"),
        Index("idx_education_records_education_type", "education_type"),
        Index("idx_education_records_is_completed", "is_completed"),
    )
