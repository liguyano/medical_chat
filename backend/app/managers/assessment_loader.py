"""量表问题加载器
作用：从 PostgreSQL 量表模板域加载 Schedule Agent 所需的问题任务。
"""

import logging
from datetime import UTC, datetime

from medagent.agents.service_agent.schedule_agent import QuestionOption, QuestionTask
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AssessmentOption,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSection,
)
from app.models import base as model_base

logger = logging.getLogger(__name__)


class AssessmentQuestionLoader:
    """从已发布量表版本加载可对话问题。"""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        """初始化加载器
        Args:
            - session_factory: 可选数据库会话工厂
        """
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    async def load_questions_by_scale_codes(
        self,
        scale_codes: list[str],
    ) -> list[QuestionTask]:
        """按调用方指定顺序加载多个量表的问题
        作用：仅加载当前生效的已发布版本，排除派生计算题。
        """
        if not scale_codes:
            return []

        tasks: list[QuestionTask] = []
        with self._new_session() as db:
            for scale_code in scale_codes:
                scale = db.scalar(
                    select(AssessmentScale).where(
                        AssessmentScale.scale_code == scale_code,
                        AssessmentScale.deleted == 0,
                    )
                )
                if scale is None:
                    logger.warning("量表不存在: %s", scale_code)
                    continue

                version = self._get_active_version(db, scale.id)
                if version is None:
                    logger.warning("量表没有当前生效的已发布版本: %s", scale_code)
                    continue
                tasks.extend(self._load_version_questions(db, scale_code, version.id))
        return tasks

    @staticmethod
    def _get_active_version(
        db: Session,
        scale_id: int,
    ) -> AssessmentScaleVersion | None:
        """查找当前生效的最新已发布版本。"""
        now = datetime.now(UTC)
        return db.scalar(
            select(AssessmentScaleVersion)
            .where(
                AssessmentScaleVersion.scale_id == scale_id,
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
            .order_by(
                AssessmentScaleVersion.effective_time.desc().nullslast(),
                AssessmentScaleVersion.id.desc(),
            )
            .limit(1)
        )

    @staticmethod
    def _load_version_questions(
        db: Session,
        scale_code: str,
        version_id: int,
    ) -> list[QuestionTask]:
        """加载一个量表版本的问题、分组和选项。"""
        rows = db.execute(
            select(AssessmentQuestion, AssessmentSection.section_name)
            .outerjoin(
                AssessmentSection,
                AssessmentSection.id == AssessmentQuestion.section_id,
            )
            .where(
                AssessmentQuestion.scale_version_id == version_id,
                AssessmentQuestion.derived.is_(False),
                AssessmentQuestion.deleted == 0,
            )
            .order_by(
                AssessmentSection.sort_no.asc().nullsfirst(),
                AssessmentQuestion.sort_no.asc(),
                AssessmentQuestion.id.asc(),
            )
        ).all()
        question_ids = [question.id for question, _ in rows]
        option_map: dict[int, list[QuestionOption]] = {
            question_id: [] for question_id in question_ids
        }
        if question_ids:
            options = db.scalars(
                select(AssessmentOption)
                .where(
                    AssessmentOption.question_id.in_(question_ids),
                    AssessmentOption.deleted == 0,
                )
                .order_by(AssessmentOption.question_id, AssessmentOption.sort_no)
            ).all()
            for option in options:
                option_map[option.question_id].append(
                    QuestionOption(
                        option_code=option.option_code,
                        option_label=option.option_label,
                        option_value=option.option_value,
                        clinical_score=(
                            float(option.clinical_score)
                            if option.clinical_score is not None
                            else None
                        ),
                        requires_follow_up=option.requires_follow_up,
                    )
                )

        return [
            QuestionTask(
                question_id=question.id,
                question_code=question.question_code,
                question_name=question.question_name,
                patient_text=question.patient_text,
                question_type=question.question_type,
                required=question.required,
                sort_no=question.sort_no,
                section_name=section_name,
                scale_code=scale_code,
                options=option_map[question.id],
            )
            for question, section_name in rows
        ]
