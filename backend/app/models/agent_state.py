"""智能体状态快照模型
作用：定义智能体状态快照表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, TIMESTAMP, CheckConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class AgentState(Base):
    """智能体状态快照表
    作用：用于故障恢复和调试
    """
    __tablename__ = "agent_states"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("dialog_sessions.session_id", ondelete="CASCADE"), nullable=False)
    state_snapshot = Column(JSONB, nullable=False, comment="智能体状态快照")
    snapshot_reason = Column(String(50), nullable=False, comment="快照原因")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "snapshot_reason IN ('periodic', 'before_error', 'manual')",
            name="chk_snapshot_reason"
        ),
        Index("idx_agent_states_session_id", "session_id"),
        Index("idx_agent_states_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
    )
