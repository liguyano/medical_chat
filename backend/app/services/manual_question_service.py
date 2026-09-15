"""题库人工采集标记：只描述采集责任，不创建答案或呼叫事件。"""

from typing import Any, TypeVar

from sqlalchemy import func, select

from app.models import base as model_base
from app.models.assessment_template import AssessmentQuestion

T = TypeVar("T")


def requires_manual(question: Any) -> bool:
    """只有显式布尔 true 才是人工题，缺省与非法历史值不升级为人工。"""
    rule = getattr(question, "validation_rule", None)
    return isinstance(rule, dict) and rule.get("manual_required") is True


def automatic_question_condition():
    """SQL 与 Python 使用相同的严格布尔判定，兼容 SQL NULL。"""
    return ~func.coalesce(
        AssessmentQuestion.validation_rule.contains({"manual_required": True}), False
    )


def filter_manual_tasks(tasks: list[T]) -> list[T]:
    """过滤旧 Redis 计划中的人工题，避免配置更新后继续追问。"""
    if not tasks or model_base.SessionLocal is None:
        return tasks
    with model_base.SessionLocal() as db:
        manual_ids = set(
            db.scalars(
                select(AssessmentQuestion.id).where(
                    AssessmentQuestion.id.in_([task.question_id for task in tasks]),
                    ~automatic_question_condition(),
                    AssessmentQuestion.deleted == 0,
                )
            ).all()
        )
    return [task for task in tasks if task.question_id not in manual_ids]
