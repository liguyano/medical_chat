"""字段抽取结果写入器
作用：封装 ORM 写入逻辑，支持 upsert submission/answer/answer_option/score
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentScore,
    AssessmentSubmission,
)
from app.models import base as model_base

logger = logging.getLogger(__name__)


class ExtractionResultWriter:
    """字段抽取结果写入器
    作用：将抽取结果写入 PostgreSQL，支持增量 merge
    """

    def __init__(self, session_factory: sessionmaker[Session] | None = None):
        """初始化写入器
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

    async def get_previous_extraction(self, submission_id: int) -> dict[int, dict]:
        """读取上次抽取结果
        作用：获取历史抽取字段，用于增量更新
        Args:
            - submission_id: 提交记录ID
        Return:
            - {question_id: {"answer": "...", "confidence": 0.90, "source_turns": [5, 6]}}
        """
        with self._new_session() as db:
            answers = (
                db.execute(
                    select(AssessmentAnswer).where(
                        AssessmentAnswer.submission_id == submission_id,
                        AssessmentAnswer.deleted == 0,
                    )
                )
                .scalars()
                .all()
            )
            answer_ids = [answer.id for answer in answers]
            option_rows = (
                db.execute(
                    select(AssessmentAnswerOption).where(
                        AssessmentAnswerOption.assessment_answer_id.in_(answer_ids),
                        AssessmentAnswerOption.selected_flag.is_(True),
                        AssessmentAnswerOption.deleted == 0,
                    )
                ).scalars().all()
                if answer_ids
                else []
            )
            options_by_answer: dict[int, list[str]] = {}
            for option in option_rows:
                options_by_answer.setdefault(option.assessment_answer_id, []).append(
                    option.option_code_snapshot
                )

            result = {}
            for ans in answers:
                # 提取答案值
                answer_value = next(
                    (
                        value
                        for value in (
                            ans.answer_text,
                            ans.answer_number,
                            ans.answer_boolean,
                            ans.answer_date,
                            ans.answer_time,
                            ans.answer_datetime,
                        )
                        if value is not None
                    ),
                    None,
                )

                selected_options = options_by_answer.get(ans.id, [])
                # 空行不进入模型上下文；无效答案仍由查询接口展示给人工。
                if answer_value is None and not selected_options:
                    continue
                result[ans.question_id] = {
                    "answer": answer_value,
                    "answer_type": ans.answer_type,
                    "selected_option_codes": selected_options,
                    "confidence": float(ans.extraction_confidence or 0.0),
                    "source_turns": ans.source_message_ids or [],
                    "value_source": ans.value_source,
                }

            return result

    async def upsert_submission(
        self,
        interaction_session_id: int,
        assessment_instance_id: int,
        extraction_result,
        total_question_count: int | None = None,
        invalid_answers: list[dict] | None = None,
        creator: str = "system",
    ) -> AssessmentSubmission:
        """创建或更新 AI 提交记录
        作用：首次创建 or 更新已有 AI submission
        Args:
            - interaction_session_id: 交互会话ID
            - assessment_instance_id: 评估实例ID
            - extraction_result: ExtractionResult 对象
            - creator: 创建者
        Return:
            - AssessmentSubmission 对象
        """
        with self._new_session() as db:
            try:
                # 查找是否已有 AI 提交
                existing = db.scalar(
                    select(AssessmentSubmission).where(
                        AssessmentSubmission.assessment_instance_id == assessment_instance_id,
                        AssessmentSubmission.submission_type == "ai_extraction",
                        AssessmentSubmission.deleted == 0,
                    )
                )

                existing_question_ids = set(
                    db.scalars(
                        select(AssessmentAnswer.question_id).where(
                            AssessmentAnswer.submission_id == existing.id,
                            AssessmentAnswer.deleted == 0,
                        )
                    ).all()
                    if existing
                    else []
                )
                extracted_question_ids = {
                    answer.question_id
                    for answer in extraction_result.extracted_answers
                    if answer.answer_value is not None or answer.selected_option_codes
                }
                total_questions = total_question_count or len(
                    existing_question_ids | extracted_question_ids
                )
                answered_questions = len(existing_question_ids | extracted_question_ids)

                submission_status = (
                    "completed" if answered_questions == total_questions else "in_progress"
                )

                if existing:
                    # 更新
                    existing.confidence_score = Decimal(str(extraction_result.overall_confidence))
                    existing.total_question_count = total_questions
                    existing.answered_question_count = answered_questions
                    existing.submission_status = submission_status
                    existing.invalid_answers = invalid_answers or existing.invalid_answers
                    existing.updator = creator
                    existing.update_time = datetime.now(UTC)

                    db.commit()
                    db.refresh(existing)

                    logger.info(
                        f"[ExtractionResultWriter] 更新提交记录: id={existing.id}, "
                        f"answered={answered_questions}/{total_questions}"
                    )
                    return existing

                else:
                    # 创建
                    from uuid import uuid4

                    submission = AssessmentSubmission(
                        submission_no=f"SUB-{uuid4().hex[:16].upper()}",
                        assessment_instance_id=assessment_instance_id,
                        submission_type="ai_extraction",
                        submitter_type="ai",
                        submission_status=submission_status,
                        confidence_score=Decimal(str(extraction_result.overall_confidence)),
                        total_question_count=total_questions,
                        answered_question_count=answered_questions,
                        invalid_answers=invalid_answers,
                        interaction_session_id=interaction_session_id,
                        creator=creator,
                    )

                    db.add(submission)
                    db.commit()
                    db.refresh(submission)

                    logger.info(
                        f"[ExtractionResultWriter] 创建提交记录: id={submission.id}, "
                        f"answered={answered_questions}/{total_questions}"
                    )
                    return submission

            except Exception:
                db.rollback()
                logger.exception("[ExtractionResultWriter] upsert_submission 失败")
                raise

    async def upsert_answers(
        self,
        submission_id: int,
        extracted_answers: list,
        creator: str = "system",
    ) -> list[AssessmentAnswer]:
        """写入或更新答案（增量 merge）
        作用：根据 value_source 判断是否覆盖护士修正的答案
        Args:
            - submission_id: 提交记录ID
            - extracted_answers: ExtractedAnswer 列表
            - creator: 创建者
        Return:
            - AssessmentAnswer 列表
        """
        with self._new_session() as db:
            try:
                results = []

                for ans in extracted_answers:
                    # 检查是否已存在（增量 merge 逻辑）
                    existing = db.scalar(
                        select(AssessmentAnswer).where(
                            AssessmentAnswer.submission_id == submission_id,
                            AssessmentAnswer.question_id == ans.question_id,
                            AssessmentAnswer.deleted == 0,
                        )
                    )

                    # 如果已存在且是护士修正的，跳过不覆盖
                    if existing and existing.value_source == "nurse_corrected":
                        logger.info(
                            f"[ExtractionResultWriter] 跳过护士修正字段: "
                            f"question_id={ans.question_id}, submission_id={submission_id}"
                        )
                        results.append(existing)
                        continue

                    # 准备数据
                    answer_data = {
                        "submission_id": submission_id,
                        "question_id": ans.question_id,
                        "answer_type": ans.answer_type,
                        "answer_text": (
                            str(ans.answer_value).strip()
                            if ans.answer_type == "text"
                            and isinstance(ans.answer_value, str)
                            and ans.answer_value.strip()
                            else None
                        ),
                        "answer_number": (
                            Decimal(str(ans.answer_value))
                            if ans.answer_type == "number"
                            and ans.answer_value is not None
                            else None
                        ),
                        "answer_boolean": (
                            bool(ans.answer_value)
                            if ans.answer_type == "boolean" and ans.answer_value is not None
                            else None
                        ),
                        "answer_date": (
                            ans.answer_value
                            if ans.answer_type == "date"
                            and ans.answer_value is not None
                            else None
                        ),
                        "answer_unit": ans.extra_inputs.get("unit"),
                        "clinical_score": (
                            Decimal(str(ans.clinical_score))
                            if ans.clinical_score is not None
                            else None
                        ),
                        "source_message_ids": ans.source_message_ids,
                        "extraction_confidence": Decimal(str(ans.extraction_confidence)),
                        "value_source": "ai_extracted",
                        "updator": creator,
                        "update_time": datetime.now(UTC),
                    }

                    if existing:
                        # 更新
                        for key, value in answer_data.items():
                            if key not in ["submission_id", "question_id"]:
                                setattr(existing, key, value)

                        db.commit()
                        db.refresh(existing)
                        results.append(existing)
                        logger.debug(
                            f"[ExtractionResultWriter] 更新答案: question_id={ans.question_id}"
                        )

                    else:
                        # 创建
                        answer_data["creator"] = creator
                        new_answer = AssessmentAnswer(**answer_data)
                        db.add(new_answer)
                        db.flush()  # 获取 ID
                        results.append(new_answer)
                        logger.debug(
                            f"[ExtractionResultWriter] 创建答案: question_id={ans.question_id}"
                        )

                db.commit()
                return results

            except Exception:
                db.rollback()
                logger.exception("[ExtractionResultWriter] upsert_answers 失败")
                raise

    async def upsert_answer_options(
        self,
        answer_id: int,
        question_id: int,
        selected_option_codes: list[str],
        extra_inputs: dict,
        creator: str = "system",
    ) -> list[AssessmentAnswerOption]:
        """写入选项明细（单选/多选题）
        作用：记录选中的选项及附加输入
        Args:
            - answer_id: 答案记录ID
            - selected_option_codes: 选中的选项编码列表
            - question_id: 问题ID
            - extra_inputs: 附加输入
            - creator: 创建者
        Return:
            - AssessmentAnswerOption 列表
        """
        with self._new_session() as db:
            try:
                # 删除旧选项（简化处理，后续可优化为 upsert）
                from app.models import AssessmentAnswerOption

                db.query(AssessmentAnswerOption).filter(
                    AssessmentAnswerOption.assessment_answer_id == answer_id
                ).delete()

                from app.models.assessment_template import AssessmentOption

                definitions = {
                    option.option_code: option
                    for option in db.scalars(
                        select(AssessmentOption).where(
                            AssessmentOption.question_id == question_id,
                            AssessmentOption.option_code.in_(selected_option_codes),
                            AssessmentOption.deleted == 0,
                        )
                    ).all()
                }
                results = []
                for code in selected_option_codes:
                    definition = definitions.get(code)
                    if definition is None:
                        logger.warning(f"选项定义缺失: question={question_id} code={code}")
                        continue

                    option = AssessmentAnswerOption(
                        assessment_answer_id=answer_id,
                        option_id=definition.id,
                        option_code_snapshot=code,
                        option_label_snapshot=definition.option_label,
                        clinical_score=definition.clinical_score,
                        extra_text=extra_inputs.get("text"),
                        extra_number=(
                            Decimal(str(extra_inputs["number"]))
                            if extra_inputs.get("number")
                            else None
                        ),
                        extra_unit=extra_inputs.get("unit"),
                        selected_flag=True,
                        creator=creator,
                    )

                    db.add(option)
                    results.append(option)

                db.commit()
                logger.debug(
                    f"[ExtractionResultWriter] 写入选项明细: "
                    f"answer_id={answer_id}, count={len(results)}"
                )
                return results

            except Exception:
                db.rollback()
                logger.exception("[ExtractionResultWriter] upsert_answer_options 失败")
                raise

    async def calculate_scores(
        self,
        submission_id: int,
        scale_version_id: int,
        creator: str = "system",
    ) -> list[AssessmentScore]:
        """计算临床得分
        作用：汇总 clinical_score，计算 risk_level
        Args:
            - submission_id: 提交记录ID
            - scale_version_id: 量表版本ID
            - creator: 创建者
        Return:
            - AssessmentScore 列表
        """
        with self._new_session() as db:
            try:
                # TODO: 从 scale_version 加载 scoring_rules（批次B实现）
                # 这里简化处理：汇总所有 clinical_score

                answers = (
                    db.execute(
                        select(AssessmentAnswer).where(
                            AssessmentAnswer.submission_id == submission_id,
                            AssessmentAnswer.deleted == 0,
                        )
                    )
                    .scalars()
                    .all()
                )

                total_score = sum(float(ans.clinical_score or 0.0) for ans in answers)

                # 简化风险等级判断（实际需要按量表规则）
                if total_score >= 10:
                    risk_level = "high_risk"
                elif total_score >= 5:
                    risk_level = "medium_risk"
                else:
                    risk_level = "low_risk"

                calculation_detail = {
                    f"question_{ans.question_id}": float(ans.clinical_score or 0.0)
                    for ans in answers
                    if ans.clinical_score
                }

                # 删除旧得分记录
                db.query(AssessmentScore).filter(
                    AssessmentScore.submission_id == submission_id
                ).delete()

                # 创建新得分
                score = AssessmentScore(
                    submission_id=submission_id,
                    score_code="total_score",
                    score_name="总分",
                    score_type="total",
                    score_value=Decimal(str(total_score)),
                    risk_level=risk_level,
                    calculation_detail=calculation_detail,
                    creator=creator,
                )

                db.add(score)
                db.commit()
                db.refresh(score)

                logger.info(
                    f"[ExtractionResultWriter] 计算得分: submission_id={submission_id}, "
                    f"total={total_score}, risk={risk_level}"
                )
                return [score]

            except Exception:
                db.rollback()
                logger.exception("[ExtractionResultWriter] calculate_scores 失败")
                raise
