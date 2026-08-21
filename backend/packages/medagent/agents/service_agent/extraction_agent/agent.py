"""Field Extraction Agent 核心逻辑
作用：从对话历史中抽取结构化量表答案，支持重试机制和派生字段计算
"""

import asyncio
import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from .prompt import build_system_prompt, build_user_prompt
from .types import normalize_answer_type
from .validator import (
    ExtractedAnswer,
    ExtractionResult,
    InvalidExtractedAnswer,
    RawExtractionResult,
)

logger = logging.getLogger(__name__)


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
        system_prompt = build_system_prompt(scale_version, questions)
        user_prompt = build_user_prompt(
            previous_extraction, history_summary, new_dialog
        )

        logger.info(
            f"[Extraction Agent] 调用 LLM: session={self.session_id}, "
            f"previous_fields={len(previous_extraction)}, "
            f"new_dialog_turns={len(new_dialog)}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 先让供应商返回对象，再逐条校验答案。不能用整个 ExtractionResult
        # 一次性校验，否则一个坏字段会丢弃同批所有有效字段。
        structured = self.model.with_structured_output(RawExtractionResult)
        raw_result = await structured.ainvoke(messages)
        if isinstance(raw_result, ExtractionResult):
            result = raw_result
        else:
            raw = (
                raw_result.model_dump(mode="json")
                if isinstance(raw_result, RawExtractionResult)
                else self._coerce_object(raw_result)
            )
            valid_answers: list[ExtractedAnswer] = []
            invalid_answers: list[InvalidExtractedAnswer] = []
            for item in raw.get("extracted_answers", []) or []:
                if not isinstance(item, dict):
                    invalid_answers.append(
                        InvalidExtractedAnswer(
                            raw_answer={"value": item},
                            error="字段结果不是对象",
                        )
                    )
                    continue
                try:
                    normalized_item = {
                        **item,
                        "answer_type": normalize_answer_type(item["answer_type"]),
                    }
                    valid_answers.append(ExtractedAnswer.model_validate(normalized_item))
                except Exception as exc:  # noqa: BLE001
                    invalid_answers.append(
                        InvalidExtractedAnswer(
                            question_id=item.get("question_id"),
                            question_code=item.get("question_code"),
                            answer_type=item.get("answer_type"),
                            raw_answer=item,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    )
            result = ExtractionResult.model_validate(
                {
                    **raw,
                    "extracted_answers": valid_answers,
                    "invalid_answers": invalid_answers,
                }
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
