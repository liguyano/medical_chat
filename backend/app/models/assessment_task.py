"""评估任务模型
作用：定义评估任务表的ORM模型
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, TIMESTAMP, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class AssessmentTask(Base):
    """评估任务表
    作用：记录医护端创建的评估任务
    """
    __tablename__ = "assessment_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_no = Column(String(32), unique=True, nullable=False, comment="任务编号")
    patient_id = Column(BigInteger, nullable=False, comment="患者ID")
    nurse_id = Column(BigInteger, nullable=False, comment="创建任务的护士ID")
    department_id = Column(BigInteger, nullable=False, comment="科室ID")
    form_ids = Column(JSONB, nullable=False, comment="量表ID列表")
    task_type = Column(String(20), nullable=False, comment="任务类型")
    status = Column(String(20), nullable=False, default="pending", comment="任务状态")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "task_type IN ('questionnaire', 'ai_dialog')",
            name="chk_task_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'cancelled')",
            name="chk_status"
        ),
        Index("idx_assessment_tasks_patient_id", "patient_id"),
        Index("idx_assessment_tasks_nurse_id", "nurse_id"),
        Index("idx_assessment_tasks_status", "status"),
        Index("idx_assessment_tasks_created_at", "created_at", postgresql_ops={"created_at": "DESC"}),
    )
