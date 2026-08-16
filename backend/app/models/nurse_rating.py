"""护理评分模型
作用：定义护理评分表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, TIMESTAMP, CheckConstraint, Index, ForeignKey
from app.models.base import Base


class NurseRating(Base):
    """护理评分表
    作用：用于收集护士对AI对话的反馈
    """
    __tablename__ = "nurse_ratings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(String(64), ForeignKey("dialog_messages.message_id", ondelete="CASCADE"), nullable=False)
    nurse_id = Column(BigInteger, nullable=False)
    rating_type = Column(String(20), nullable=False, comment="评分类型")
    comment = Column(Text, nullable=True, comment="护士意见")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "rating_type IN ('like', 'dislike')",
            name="chk_rating_type"
        ),
        Index("idx_nurse_ratings_message_id", "message_id"),
        Index("idx_nurse_ratings_nurse_id", "nurse_id"),
        Index("idx_nurse_ratings_rating_type", "rating_type"),
        Index("idx_nurse_ratings_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
    )
