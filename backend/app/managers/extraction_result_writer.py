"""字段抽取结果写入器
作用：封装 ORM 写入逻辑，支持 upsert submission/answer/answer_option/score
"""

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AssessmentAnswer,
    AssessmentAnswerOption,
    AssessmentRule,
    AssessmentScore,
    AssessmentSubmission,
)
from app.models import base as model_base
from app.models.assessment_template import AssessmentQuestion
from app.services.manual_question_service import automatic_question_condition

logger = logging.getLogger(__name__)



def _selected_answer_score(
    answer: AssessmentAnswer,
    selected_options: list[AssessmentAnswerOption],
) -> Decimal | None:
    """从有效答案的选项快照取得真实临床分值。

    选择题必须有已选选项，且各选项都定义了分值；明确选择 0 分是合法结果。
    非选择题沿用已经计算并写入答案的临床分数，不直接使用患者输入数值。
    """
    if answer.answer_type in {"single_choice", "multiple_choice"}:
        if not selected_options or any(
            option.clinical_score is None for option in selected_options
        ):
            return None
        return sum(
            (Decimal(str(option.clinical_score)) for option in selected_options),
            Decimal(0),
        )
    return (
        Decimal(str(answer.clinical_score))
        if answer.clinical_score is not None
        else None
    )


def _score_rule_matches(expression: str, total: Decimal) -> bool:
    """只识别已有量表导入器支持的 total_score 简单比较表达式。"""
    clauses = re.split(r"\s+and\s+", expression.strip(), flags=re.IGNORECASE)
    for clause in clauses:
        match = re.fullmatch(
            r"\s*total_score\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*",
            clause,
        )
        if match is None:
            return False
        threshold = Decimal(match.group(2))
        operator = match.group(1)
        if not {
            ">=": total >= threshold,
            "<=": total <= threshold,
            "==": total == threshold,
            ">": total > threshold,
            "<": total < threshold,
        }[operator]:
            return False
    return bool(clauses)


def recalculate_submission_score(
    db: Session,
    submission_id: int,
    scale_version_id: int,
    *,
    creator: str = "system",
) -> list[AssessmentScore]:
    """重新汇总某一次提交的有效计分答案；由调用方决定何时提交事务。

    未完成的必填题、没有计分题和缺失选项分值必须返回空结果，
    不能将 None 隐式转换为 0 分，也不能套用跨量表通用风险阈值。
    """
    from app.services.assessment_progress_service import (
        valid_assessment_answer_condition,
    )

    submission = db.get(AssessmentSubmission, submission_id)
    if submission is None:
        raise ValueError(f"评估提交不存在: {submission_id}")

    required_ids = set(
        db.scalars(
            select(AssessmentQuestion.id).where(
                AssessmentQuestion.scale_version_id == scale_version_id,
                AssessmentQuestion.required.is_(True),
                AssessmentQuestion.derived.is_(False),
                AssessmentQuestion.deleted == 0,
            )
        ).all()
    )
    scored_questions = list(
        db.scalars(
            select(AssessmentQuestion).where(
                AssessmentQuestion.scale_version_id == scale_version_id,
                AssessmentQuestion.scored.is_(True),
                AssessmentQuestion.derived.is_(False),
                AssessmentQuestion.deleted == 0,
            )
        ).all()
    )
    answers = list(
        db.scalars(
            select(AssessmentAnswer).where(
                AssessmentAnswer.submission_id == submission_id,
                AssessmentAnswer.deleted == 0,
                valid_assessment_answer_condition(),
            )
        ).all()
    )
    answers_by_question = {answer.question_id: answer for answer in answers}

    def clear_incomplete_score() -> list[AssessmentScore]:
        """清除旧的无效总分，防止报告把尚未计算的量表显示为 0 分。"""
        db.execute(
            delete(AssessmentScore).where(
                AssessmentScore.submission_id == submission_id
            )
        )
        submission.total_score = None
        submission.risk_level = None
        submission.result_summary = None
        submission.updator = creator
        return []

    if (
        not scored_questions
        or required_ids - answers_by_question.keys()
        or {question.id for question in scored_questions} - answers_by_question.keys()
    ):
        return clear_incomplete_score()

    scored_answers = [
        answers_by_question[question.id]
        for question in scored_questions
        if question.id in answers_by_question
    ]
    if not scored_answers:
        return clear_incomplete_score()

    option_answer_ids = [
        answer.id
        for answer in scored_answers
        if answer.answer_type in {"single_choice", "multiple_choice"}
    ]
    selected_by_answer: dict[int, list[AssessmentAnswerOption]] = {}
    if option_answer_ids:
        selected_options = db.scalars(
            select(AssessmentAnswerOption).where(
                AssessmentAnswerOption.assessment_answer_id.in_(option_answer_ids),
                AssessmentAnswerOption.selected_flag.is_(True),
                AssessmentAnswerOption.deleted == 0,
            )
        ).all()
        for option in selected_options:
            selected_by_answer.setdefault(
                option.assessment_answer_id, []
            ).append(option)

    scores_by_question: dict[str, float] = {}
    total_score = Decimal(0)
    incomplete = False
    for answer in scored_answers:
        score = _selected_answer_score(
            answer, selected_by_answer.get(answer.id, [])
        )
        if answer.answer_type in {"single_choice", "multiple_choice"}:
            # 重算并保存每题的选项累计分，以供报告原始明细直接展示。
            answer.clinical_score = score
        if score is None:
            incomplete = True
            continue
        total_score += score
        scores_by_question[f"question_{answer.question_id}"] = float(score)

    if incomplete:
        return clear_incomplete_score()

    result_summary = None
    risk_level = None
    rules = db.scalars(
        select(AssessmentRule).where(
            AssessmentRule.scale_version_id == scale_version_id,
            AssessmentRule.deleted == 0,
            AssessmentRule.status.in_(("启用", "active", "enabled")),
        ).order_by(AssessmentRule.priority.asc(), AssessmentRule.id.asc())
    ).all()
    for rule in rules:
        expression = (rule.condition_expression or {}).get("expression")
        if not isinstance(expression, str) or not _score_rule_matches(
            expression, total_score
        ):
            continue
        payload = rule.result_payload or {}
        result_summary = str(
            payload.get("result") or payload.get("summary") or ""
        ) or None
        raw_risk = payload.get("risk_level")
        risk_level = str(raw_risk) if raw_risk is not None else None
        break

    db.execute(
        delete(AssessmentScore).where(
            AssessmentScore.submission_id == submission_id
        )
    )
    score = AssessmentScore(
        submission_id=submission_id,
        score_code="total_score",
        score_name="总分",
        score_type="total",
        score_value=total_score,
        risk_level=risk_level,
        interpretation=result_summary,
        calculation_detail=scores_by_question,
        creator=creator,
        updator=creator,
    )
    db.add(score)
    submission.total_score = total_score
    submission.risk_level = risk_level
    submission.result_summary = result_summary
    submission.updator = creator
    return [score]



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
        """按当前已选选项和量表专属规则计算临床得分。"""
        with self._new_session() as db:
            try:
                scores = recalculate_submission_score(
                    db, submission_id, scale_version_id, creator=creator
                )
                db.commit()
                for score in scores:
                    db.refresh(score)
                logger.info(
                    "[ExtractionResultWriter] 重新计算得分: submission_id=%s, total=%s",
                    submission_id,
                    scores[0].score_value if scores else "未完成计分",
                )
                return scores
            except Exception:
                db.rollback()
                logger.exception(
                    "[ExtractionResultWriter] calculate_scores 失败"
                )
                raise
