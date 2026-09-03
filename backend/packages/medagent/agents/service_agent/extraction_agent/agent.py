"""Field Extraction Agent 核心逻辑
作用：从对话历史中抽取结构化量表答案，支持重试机制和派生字段计算
"""

import asyncio
import json
import logging
from datetime import date
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from .prompt import build_focused_user_prompt, build_system_prompt, build_user_prompt
from .types import normalize_answer_type
from .validator import (
    ExtractedAnswer,
    ExtractionCandidate,
    ExtractionResult,
    InvalidExtractedAnswer,
    RawExtractionResult,
)

logger = logging.getLogger(__name__)

EXPLICIT_UNKNOWN_VALUES = {
    "不知道",
    "我不知道",
    "这个不知道",
    "这个我不知道",
    "不清楚",
    "我不清楚",
    "这个我不清楚",
    "不太清楚",
    "我不太清楚",
    "记不清",
    "记不清了",
    "我记不清",
    "我记不清了",
    "不记得",
    "不记得了",
    "我不记得",
    "我不记得了",
    "记不得",
    "记不得了",
    "忘了",
    "我忘了",
    "忘记了",
    "我忘记了",
    "说不准",
    "我说不准",
    "不确定",
    "我不确定",
    "不太确定",
    "我不太确定",
    "想不起来",
    "我想不起来",
}


class FieldExtractionAgent:
    """字段抽取智能体
    作用：调用 LLM 从对话中抽取结构化字段，支持增量更新和重试
    """

    def __init__(
        self,
        session_id: str,
        scale_codes: list[str],
        model: BaseChatModel,
    ):
        """初始化 Field Extraction Agent
        Args:
            - session_id: 会话ID
            - scale_codes: 量表编码列表
            - model: LangChain BaseChatModel（temperature/timeout 等在模型构造时注入）
        """
        self.session_id = session_id
        self.scale_codes = scale_codes
        self.model = model

    async def extract_from_dialog(
        self,
        previous_extraction: dict[int, dict],
        history_summary: str,
        new_dialog: list[dict],
        scale_version: dict,
        questions: list[dict],
    ) -> ExtractionResult:
        """从对话中抽取字段（增量+摘要方案）
        作用：调用 LLM 分析历史抽取字段 + 对话摘要 + 新对话，返回结构化结果
        Args:
            - previous_extraction: 历史抽取字段
              {question_id: {"answer": "...", "confidence": 0.90, ...}}
            - history_summary: 历史对话摘要（2-3句话）
            - new_dialog: 新对话列表 [{"turn": 8, "patient": "...", "ai": "..."}]
            - scale_version: 量表版本信息
            - questions: 问题列表
        Return:
            - ExtractionResult 对象
        Raises:
            - ValidationError: JSON Schema 校验失败
            - openai.APITimeoutError: LLM 超时
        """
        direct_unknown = self._build_bound_explicit_unknown_result(
            new_dialog=new_dialog,
            questions=questions,
        )
        if direct_unknown is not None:
            logger.info(
                "[Extraction Agent] 当前题收到明确未知回答，直接记录: session=%s question=%s",
                self.session_id,
                direct_unknown.extracted_answers[0].question_id,
            )
            return self._calculate_derived_fields(direct_unknown)

        system_prompt = build_system_prompt(scale_version, questions)
        user_prompt = build_user_prompt(
            previous_extraction, history_summary, new_dialog
        )

        logger.info(
            f"[Extraction Agent] 调用 LLM: session={self.session_id}, "
            f"previous_fields={len(previous_extraction)}, "
            f"new_dialog_turns={len(new_dialog)}"
        )

        source_message_ids = [
            str(item.get("message_id"))
            for item in new_dialog
            if item.get("message_id")
        ]
        result = await self._invoke_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            questions=questions,
            source_message_ids=source_message_ids,
        )

        # 首次没有形成有效答案时，只对当前实际问句执行一次结构化重判。
        if not result.extracted_answers and new_dialog:
            current_question_id = new_dialog[-1].get("current_question_id")
            focused_questions = [
                question
                for question in questions
                if current_question_id is None
                or question.get("question_id") == current_question_id
            ]
            if focused_questions:
                logger.info(
                    "[Extraction Agent] 首次无有效答案，执行当前问句聚焦重判: "
                    "session=%s, current_question_id=%s",
                    self.session_id,
                    current_question_id,
                )
                result = await self._invoke_structured(
                    system_prompt=build_system_prompt(
                        scale_version,
                        focused_questions,
                    ),
                    user_prompt=build_focused_user_prompt(new_dialog),
                    questions=focused_questions,
                    source_message_ids=source_message_ids,
                )

        # 计算派生字段
        result = self._calculate_derived_fields(result)

        logger.info(
            "[Extraction Agent] 真实模型结构化响应成功: session=%s, fields=%s, confidence=%.3f",
            self.session_id,
            len(result.extracted_answers),
            result.overall_confidence,
        )
        return result

    async def _invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        questions: list[dict],
        source_message_ids: list[str],
    ) -> ExtractionResult:
        """调用结构化模型并补齐后端答案契约。"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        structured = self.model.with_structured_output(RawExtractionResult)
        raw_result = await structured.ainvoke(messages)
        if isinstance(raw_result, ExtractionResult):
            return raw_result
        raw = (
            raw_result
            if isinstance(raw_result, RawExtractionResult)
            else RawExtractionResult.model_validate(self._coerce_object(raw_result))
        )
        return self._build_result(
            raw,
            questions=questions,
            source_message_ids=source_message_ids,
        )

    @classmethod
    def _build_bound_explicit_unknown_result(
        cls,
        *,
        new_dialog: list[dict],
        questions: list[dict],
    ) -> ExtractionResult | None:
        """当前问答已绑定题目时，将患者明确未知直接转换为可持久化答案。"""
        if not new_dialog:
            return None
        turn = new_dialog[-1]
        question_id = turn.get("current_question_id")
        if question_id is None:
            return None
        explicit_unknown = cls._explicit_unknown_text(turn.get("patient"))
        if explicit_unknown is None:
            return None
        question = next(
            (
                item
                for item in questions
                if item.get("question_id") is not None
                and int(item["question_id"]) == int(question_id)
            ),
            None,
        )
        if question is None:
            return None
        message_id = turn.get("message_id")
        raw = RawExtractionResult(
            answers=[
                ExtractionCandidate(
                    question_id=int(question_id),
                    value=explicit_unknown,
                    evidence=str(turn.get("patient") or explicit_unknown).strip(),
                    confidence=1.0,
                )
            ]
        )
        return cls._build_result(
            raw,
            questions=[question],
            source_message_ids=[str(message_id)] if message_id else [],
        )

    @classmethod
    def _build_result(
        cls,
        raw: RawExtractionResult,
        *,
        questions: list[dict],
        source_message_ids: list[str],
    ) -> ExtractionResult:
        """将最小模型候选转换为现有持久化答案契约。"""
        question_by_id = {
            int(question["question_id"]): question
            for question in questions
            if question.get("question_id") is not None
        }
        valid_answers: list[ExtractedAnswer] = []
        invalid_answers: list[InvalidExtractedAnswer] = []

        for candidate in raw.answers:
            question = question_by_id.get(candidate.question_id)
            if question is None:
                invalid_answers.append(
                    cls._invalid_candidate(candidate, "题目不属于当前量表")
                )
                continue
            try:
                valid_answers.append(
                    cls._candidate_to_answer(
                        candidate,
                        question=question,
                        source_message_ids=source_message_ids,
                    )
                )
            except (TypeError, ValueError) as exc:
                invalid_answers.append(
                    cls._invalid_candidate(candidate, str(exc), question=question)
                )

        valid_ids = {answer.question_id for answer in valid_answers}
        invalid_ids = {
            item.question_id for item in invalid_answers if item.question_id is not None
        }
        confidence = (
            sum(answer.extraction_confidence for answer in valid_answers)
            / len(valid_answers)
            if valid_answers
            else 0.0
        )
        return ExtractionResult(
            extracted_answers=valid_answers,
            overall_confidence=confidence,
            missing_questions=[
                question_id
                for question_id in question_by_id
                if question_id not in valid_ids
            ],
            ambiguous_questions=sorted(invalid_ids),
            invalid_answers=invalid_answers,
        )

    @classmethod
    def _candidate_to_answer(
        cls,
        candidate: ExtractionCandidate,
        *,
        question: dict,
        source_message_ids: list[str],
    ) -> ExtractedAnswer:
        """依据题库定义补齐单个候选并规范化答案值。"""
        explicit_unknown = cls._explicit_unknown_text(candidate.value)
        if explicit_unknown is not None:
            return ExtractedAnswer(
                question_id=candidate.question_id,
                question_code=str(question.get("question_code") or candidate.question_id),
                answer_type="text",
                answer_value=explicit_unknown,
                selected_option_codes=[],
                extra_inputs={"explicit_unknown": True},
                clinical_score=None,
                extraction_confidence=max(candidate.confidence, 0.95),
                source_message_ids=list(dict.fromkeys(source_message_ids)),
                reasoning=candidate.evidence.strip(),
            )

        raw_type = str(question.get("answer_type") or "text")
        try:
            answer_type = normalize_answer_type(raw_type)
        except ValueError:
            answer_type = "text"

        selected_option_codes: list[str] = []
        answer_value: str | float | bool | date | None = None
        if answer_type in {"single_choice", "multiple_choice"}:
            selected_option_codes = cls._map_option_codes(
                candidate.value,
                options=list(question.get("options") or []),
                multiple=answer_type == "multiple_choice",
            )
        elif answer_type == "number":
            if isinstance(candidate.value, bool) or isinstance(candidate.value, list):
                raise ValueError("数值题候选不是数值")
            answer_value = float(candidate.value)
        elif answer_type == "boolean":
            answer_value = cls._normalize_boolean(candidate.value)
        elif answer_type == "date":
            if not isinstance(candidate.value, str):
                raise ValueError("日期题候选不是日期字符串")
            answer_value = date.fromisoformat(candidate.value.strip())
        else:
            if isinstance(candidate.value, list):
                answer_value = "、".join(candidate.value)
            else:
                answer_value = str(candidate.value).strip()
            if not answer_value:
                raise ValueError("文本题候选为空")

        return ExtractedAnswer(
            question_id=candidate.question_id,
            question_code=str(question.get("question_code") or candidate.question_id),
            answer_type=answer_type,
            answer_value=answer_value,
            selected_option_codes=selected_option_codes,
            extra_inputs={},
            clinical_score=None,
            extraction_confidence=candidate.confidence,
            source_message_ids=list(dict.fromkeys(source_message_ids)),
            reasoning=candidate.evidence.strip(),
        )

    @staticmethod
    def _explicit_unknown_text(value: Any) -> str | None:
        """识别患者明确表示未知的回答，并保留其简短原值。"""
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        normalized = text.casefold().replace(" ", "").strip("。！？，,.!?；;：:")
        if normalized in EXPLICIT_UNKNOWN_VALUES:
            return text.strip("。！？，,.!?；;：:")
        return None

    @staticmethod
    def _normalize_boolean(value: Any) -> bool:
        """将常见布尔表达规范化为布尔值。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, list):
            raise ValueError("布尔题候选不是单值")
        normalized = str(value).strip().casefold()
        if normalized in {"true", "1", "yes", "是", "有"}:
            return True
        if normalized in {"false", "0", "no", "否", "无", "没有"}:
            return False
        raise ValueError("布尔题候选无法识别")

    @staticmethod
    def _map_option_codes(
        value: str | float | bool | list[str],
        *,
        options: list[dict],
        multiple: bool,
    ) -> list[str]:
        """在当前题目内把编码、标签或值唯一映射为选项编码。"""
        values = value if isinstance(value, list) else [value]
        if not values:
            raise ValueError("选择题候选为空")
        if not multiple and len(values) != 1:
            raise ValueError("单选题候选包含多个值")

        codes: list[str] = []
        for raw_value in values:
            target = str(raw_value).strip().casefold()
            matched = []
            for option in options:
                aliases = {
                    str(option.get("option_code", "")).strip().casefold(),
                    str(option.get("option_label", "")).strip().casefold(),
                    str(option.get("option_value", "")).strip().casefold(),
                }
                if target and target in aliases:
                    matched.append(str(option.get("option_code") or ""))
            matched = list(dict.fromkeys(code for code in matched if code))
            if len(matched) != 1:
                raise ValueError(f"选择题候选无法唯一映射: {raw_value}")
            codes.append(matched[0])
        return list(dict.fromkeys(codes))

    @staticmethod
    def _invalid_candidate(
        candidate: ExtractionCandidate,
        error: str,
        *,
        question: dict | None = None,
    ) -> InvalidExtractedAnswer:
        """生成仅供诊断的无效候选记录。"""
        return InvalidExtractedAnswer(
            question_id=candidate.question_id,
            question_code=(str(question.get("question_code")) if question else None),
            answer_type=(str(question.get("answer_type")) if question else None),
            raw_answer=candidate.model_dump(mode="json"),
            error=error,
        )

    @staticmethod
    def _coerce_object(value) -> dict:
        """将兼容模型响应转换为 JSON 对象。"""
        if isinstance(value, dict):
            return value
        content = getattr(value, "content", value)
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        if isinstance(content, str):
            return json.loads(content)
        raise TypeError("字段抽取模型未返回 JSON 对象")

    async def extract_with_retry(
        self,
        previous_extraction: dict[int, dict],
        history_summary: str,
        new_dialog: list[dict],
        scale_version: dict,
        questions: list[dict],
        max_retries: int = 3,
    ) -> ExtractionResult | None:
        """带重试的字段抽取
        作用：最多重试 3 次，失败后返回 None（调用方需标记人工补录）
        Args:
            - max_retries: 最大重试次数
            - 其他参数同 extract_from_dialog
        Return:
            - ExtractionResult 对象 或 None（失败）
        """
        for attempt in range(max_retries):
            try:
                return await self.extract_from_dialog(
                    previous_extraction,
                    history_summary,
                    new_dialog,
                    scale_version,
                    questions,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"[Extraction Agent] 抽取失败 (attempt {attempt + 1}/{max_retries}): "
                    f"session={self.session_id}, error={type(e).__name__}: {e}"
                )
                if attempt == max_retries - 1:
                    # 最后一次失败，返回 None（调用方需标记人工补录）
                    logger.error(
                        f"[Extraction Agent] 达到最大重试次数，抽取失败: session={self.session_id}"
                    )
                    return None
                await asyncio.sleep(1)  # 间隔 1 秒重试

        return None

    def _calculate_derived_fields(self, result: ExtractionResult) -> ExtractionResult:
        """计算派生字段
        作用：根据已抽取字段计算 BMI、体重下降比例、血压分类等
        Args:
            - result: 原始抽取结果
        Return:
            - 补充派生字段后的结果
        """
        # 构建字段索引：question_code -> ExtractedAnswer
        answers_by_code = {
            ans.question_code: ans for ans in result.extracted_answers
        }

        # 1. 计算 BMI（体重 kg / 身高 m^2）
        if "body_weight" in answers_by_code and "body_height" in answers_by_code:
            weight_ans = answers_by_code["body_weight"]
            height_ans = answers_by_code["body_height"]

            if (
                weight_ans.answer_value is not None
                and height_ans.answer_value is not None
            ):
                try:
                    weight_kg = float(weight_ans.answer_value)
                    height_cm = float(height_ans.answer_value)
                    height_m = height_cm / 100.0

                    if height_m > 0:
                        bmi = weight_kg / (height_m**2)
                        logger.info(
                            f"[Extraction Agent] 计算 BMI: {bmi:.2f} "
                            f"(体重={weight_kg}kg, 身高={height_cm}cm)"
                        )

                        # 假设问题列表中有 question_code='bmi' 的题目
                        # 这里简化处理：直接追加到 extra_inputs（实际可能需要新增 answer）
                        weight_ans.extra_inputs["calculated_bmi"] = round(bmi, 2)
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    logger.warning(f"[Extraction Agent] BMI 计算失败: {e}")

        # 2. 计算体重下降比例（通常体重 - 现体重）/ 通常体重
        if "usual_weight" in answers_by_code and "body_weight" in answers_by_code:
            usual_ans = answers_by_code["usual_weight"]
            current_ans = answers_by_code["body_weight"]

            if (
                usual_ans.answer_value is not None
                and current_ans.answer_value is not None
            ):
                try:
                    usual_kg = float(usual_ans.answer_value)
                    current_kg = float(current_ans.answer_value)

                    if usual_kg > 0:
                        loss_ratio = (usual_kg - current_kg) / usual_kg
                        logger.info(
                            f"[Extraction Agent] 计算体重下降比例: {loss_ratio:.2%} "
                            f"(通常={usual_kg}kg, 现={current_kg}kg)"
                        )
                        current_ans.extra_inputs["weight_loss_ratio"] = round(
                            loss_ratio, 3
                        )
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    logger.warning(f"[Extraction Agent] 体重下降比例计算失败: {e}")

        # 3. 血压分类（收缩压/舒张压 → 正常/偏高/高血压）
        if "systolic_bp" in answers_by_code and "diastolic_bp" in answers_by_code:
            sys_ans = answers_by_code["systolic_bp"]
            dia_ans = answers_by_code["diastolic_bp"]

            if (
                sys_ans.answer_value is not None
                and dia_ans.answer_value is not None
            ):
                try:
                    systolic = float(sys_ans.answer_value)
                    diastolic = float(dia_ans.answer_value)

                    if systolic >= 140 or diastolic >= 90:
                        bp_category = "高血压"
                    elif systolic >= 130 or diastolic >= 85:
                        bp_category = "偏高"
                    else:
                        bp_category = "正常"

                    logger.info(
                        f"[Extraction Agent] 血压分类: {bp_category} "
                        f"({systolic}/{diastolic} mmHg)"
                    )
                    sys_ans.extra_inputs["bp_category"] = bp_category
                except (ValueError, TypeError) as e:
                    logger.warning(f"[Extraction Agent] 血压分类失败: {e}")

        return result
