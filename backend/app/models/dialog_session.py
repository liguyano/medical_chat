"""对话会话模型
作用：定义对话会话表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, TIMESTAMP, CheckConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class DialogSession(Base):
    """对话会话表
    作用：记录各智能体会话状态
    """
    __tablename__ = "dialog_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, comment="会话ID（进程号）")
    task_id = Column(BigInteger, ForeignKey("assessment_tasks.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(BigInteger, nullable=False)
    agent_type = Column(String(50), nullable=False, comment="智能体类型")
    status = Column(String(20), nullable=False, default="active", comment="会话状态")
    redis_state_key = Column(String(128), nullable=True, comment="Redis状态存储key")
    agent_metadata = Column(JSONB, nullable=True, comment="智能体元数据")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    last_active_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "agent_type IN ('schedule_agent', 'dialog_agent', 'extraction_agent')",
            name="chk_agent_type"
        ),
        CheckConstraint(
            "status IN ('preheating', 'active', 'paused', 'completed', 'error')",
            name="chk_session_status"
        ),
        Index("idx_dialog_sessions_session_id", "session_id"),
        Index("idx_dialog_sessions_task_id", "task_id"),
        Index("idx_dialog_sessions_status", "status"),
        Index("idx_dialog_sessions_last_active", "last_active_at", postgresql_ops={"last_active_at": "DESC"}),
    )
