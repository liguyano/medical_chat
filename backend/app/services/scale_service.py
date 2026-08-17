"""量表服务
作用：封装量表与量表题目的查询逻辑。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.assessment_template import (
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
)
from app.schemas.scale import AssessmentScaleDto

logger = logging.getLogger(__name__)


def list_published_scales(db: Session) -> list[AssessmentScaleDto]:
    """查询已发布量表列表
    作用：返回当前生效且已发布的量表版本，含非衍生题目计数，供前端量表选择使用。
    Args:
        - db: 数据库会话
    Return:
        - AssessmentScaleDto 列表
    """
    now = datetime.now(UTC)

    # 子查询：每个量表的当前生效版本（已发布 + 生效时间窗口）
    active_version_subq = (
        select(
            AssessmentScaleVersion.scale_id,
            func.max(AssessmentScaleVersion.id).label("version_id"),
        )
        .where(
            AssessmentScaleVersion.publish_status == "已发布",
            AssessmentScaleVersion.deleted == 0,
            or_(
                AssessmentScaleVersion.effective_time.is_(None),
                AssessmentScaleVersion.effective_time <= now,
            ),
            or_(
                AssessmentScaleVersion.expire_time.is_(None),
                AssessmentScaleVersion.expire_time > now,
            ),
        )
        .group_by(AssessmentScaleVersion.scale_id)
        .subquery()
    )

    # 主查询：量表 JOIN 生效版本
    scale_rows = list(
        db.execute(
            select(AssessmentScale, AssessmentScaleVersion)
            .join(
                active_version_subq,
                AssessmentScale.id == active_version_subq.c.scale_id,
            )
            .join(
                AssessmentScaleVersion,
                AssessmentScaleVersion.id == active_version_subq.c.version_id,
            )
            .where(AssessmentScale.deleted == 0)
            .order_by(AssessmentScale.id.asc())
        ).all()
    )

    result = []
    for scale, version in scale_rows:
        # 统计非衍生题目数
        question_count = db.scalar(
            select(func.count(AssessmentQuestion.id)).where(
                and_(
                    AssessmentQuestion.scale_version_id == version.id,
                    AssessmentQuestion.derived.is_(False),
                    AssessmentQuestion.deleted == 0,
                )
            )
        )
        result.append(
            AssessmentScaleDto(
                id=scale.id,
                scale_code=scale.scale_code,
                scale_name=scale.scale_name,
                form_type=scale.form_type,
                question_count=int(question_count or 0),
                version_code=version.version_code,
                description=scale.description,
            )
        )

    logger.info(f"查询已发布量表: 共 {len(result)} 个")
    return result
