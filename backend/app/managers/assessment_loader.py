"""量表问题加载器
作用：从数据库和结构化JSON文件中加载量表问题，为Schedule Agent提供任务列表。
"""
import json
import logging
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AssessmentQuestion, AssessmentScale, AssessmentScaleVersion
from app.models import base as model_base

logger = logging.getLogger(__name__)


class QuestionTask:
    """单个量表问题任务
    作用：封装量表问题的核心信息，供Schedule Agent使用
    """

    def __init__(
        self,
        question_id: int,
        question_code: str,
        question_name: str,
        patient_text: str,
        question_type: str,
        required: bool,
        sort_no: int,
        section_name: Optional[str] = None,
        scale_code: Optional[str] = None,
    ):
        self.question_id = question_id
        self.question_code = question_code
        self.question_name = question_name
        self.patient_text = patient_text  # 口语化问题文本
        self.question_type = question_type
        self.required = required
        self.sort_no = sort_no
        self.section_name = section_name
        self.scale_code = scale_code
        self.completed = False  # 是否已完成

    def to_dict(self):
        """转换为字典格式"""
        return {
            "question_id": self.question_id,
            "question_code": self.question_code,
            "question_name": self.question_name,
            "patient_text": self.patient_text,
            "question_type": self.question_type,
            "required": self.required,
            "sort_no": self.sort_no,
            "section_name": self.section_name,
            "scale_code": self.scale_code,
            "completed": self.completed,
        }

    def __repr__(self):
        return f"<QuestionTask {self.question_code}: {self.question_name}>"


class AssessmentQuestionLoader:
    """量表问题加载器
    作用：提供从数据库加载量表问题的功能
    """

    def __init__(self, session_factory: sessionmaker[Session] | None = None):
        """初始化加载器
        Args:
            - session_factory: 可选会话工厂；为空时使用全局工厂
        """
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        """创建数据库会话"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    async def load_questions_by_scale_codes(
        self, scale_codes: List[str]
    ) -> List[QuestionTask]:
        """根据量表编码列表加载所有问题
        作用：从数据库读取量表问题，过滤计算题，按顺序返回
        Args:
            - scale_codes: 量表编码列表 (例如 ["adl", "nrs2002"])
        Return:
            - questions: QuestionTask列表，按量表顺序和sort_no排序
        """
        if not scale_codes:
            logger.warning("量表编码列表为空，返回空问题列表")
            return []

        all_questions: List[QuestionTask] = []

        with self._new_session() as db:
            for scale_code in scale_codes:
                try:
                    # 1. 获取量表ID
                    scale = db.scalar(
                        select(AssessmentScale)
                        .where(
                            AssessmentScale.scale_code == scale_code,
                            AssessmentScale.deleted == 0,
                        )
                        .limit(1)
                    )

                    if not scale:
                        logger.warning(f"量表不存在: {scale_code}")
                        continue

                    # 2. 获取当前生效版本
                    version = await self._get_active_version(db, scale.id)
                    if not version:
                        logger.warning(f"量表无生效版本: {scale_code}")
                        continue

                    # 3. 读取该版本的所有问题
                    questions = list(
                        db.scalars(
                            select(AssessmentQuestion)
                            .where(
                                AssessmentQuestion.scale_version_id == version.id,
                                AssessmentQuestion.derived == False,  # 过滤计算题
                                AssessmentQuestion.deleted == 0,
                            )
                            .order_by(AssessmentQuestion.sort_no.asc())
                        ).all()
                    )

                    # 4. 转换为 QuestionTask
                    for q in questions:
                        task = QuestionTask(
                            question_id=q.id,
                            question_code=q.question_code,
                            question_name=q.question_name,
                            patient_text=q.patient_text,
                            question_type=q.question_type,
                            required=q.required,
                            sort_no=q.sort_no,
                            scale_code=scale_code,
                        )
                        all_questions.append(task)

                    logger.info(
                        f"成功加载量表问题: {scale_code}, 共{len(questions)}题"
                    )

                except Exception as e:
                    logger.error(f"加载量表问题失败: {scale_code} - {e}")
                    continue

        logger.info(f"总计加载问题: {len(all_questions)}题，来自{len(scale_codes)}个量表")
        return all_questions

    async def _get_active_version(
        self, db: Session, scale_id: int
    ) -> Optional[AssessmentScaleVersion]:
        """获取量表当前生效版本
        作用：查询 publish_status='已发布' 且在有效期内的版本
        Args:
            - db: 数据库会话
            - scale_id: 量表ID
        Return:
            - version: 生效版本，不存在返回None
        """
        from datetime import datetime, UTC

        now = datetime.now(UTC)

        version = db.scalar(
            select(AssessmentScaleVersion)
            .where(
                AssessmentScaleVersion.scale_id == scale_id,
                AssessmentScaleVersion.publish_status == "已发布",
                AssessmentScaleVersion.deleted == 0,
            )
            .where(
                (AssessmentScaleVersion.effective_time == None)
                | (AssessmentScaleVersion.effective_time <= now)
            )
            .where(
                (AssessmentScaleVersion.expire_time == None)
                | (AssessmentScaleVersion.expire_time > now)
            )
            .order_by(AssessmentScaleVersion.id.desc())
            .limit(1)
        )

        return version

    async def load_questions_from_json(
        self, scale_code: str, json_file_path: str
    ) -> List[QuestionTask]:
        """从结构化JSON文件加载问题（用于数据库尚未导入时）
        作用：直接读取 docs/structured/assessment-scales/*.json
        Args:
            - scale_code: 量表编码
            - json_file_path: JSON文件路径
        Return:
            - questions: QuestionTask列表
        """
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            questions: List[QuestionTask] = []

            # 解析 scoring.items（ADL格式）
            if "scoring" in data and "items" in data["scoring"]:
                for idx, item in enumerate(data["scoring"]["items"]):
                    task = QuestionTask(
                        question_id=0,  # JSON数据无数据库ID
                        question_code=item["id"],
                        question_name=item["label"],
                        patient_text=item["label"],  # JSON中没有口语化文本
                        question_type="single_choice",  # 默认单选
                        required=True,
                        sort_no=idx + 1,
                        scale_code=scale_code,
                    )
                    questions.append(task)

            logger.info(f"从JSON加载问题: {scale_code}, 共{len(questions)}题")
            return questions

        except Exception as e:
            logger.error(f"从JSON加载问题失败: {json_file_path} - {e}")
            return []
