"""字段抽取统一契约的纯单元测试。"""

import pytest
from pydantic import ValidationError

from medagent.agents.service_agent.extraction_agent.agent import FieldExtractionAgent
from medagent.agents.service_agent.extraction_agent.prompt import (
    build_system_prompt,
    build_user_prompt,
)
from medagent.agents.service_agent.extraction_agent.types import normalize_answer_type
from medagent.agents.service_agent.extraction_agent.validator import (
    ExtractedAnswer,
    ExtractionCandidate,
    RawExtractionResult,
)


def test_source_types_are_normalized_at_boundary() -> None:
    """中文和历史原始类型只能在边界转换为标准值。"""
    assert normalize_answer_type("多选") == "multiple_choice"
    assert normalize_answer_type("multi_choice_with_detail") == "multiple_choice"
    assert normalize_answer_type("integer") == "number"


def test_runtime_schema_does_not_accept_historical_alias() -> None:
    """运行时 Pydantic 契约不兼容旧别名。"""
    with pytest.raises(ValidationError):
        ExtractedAnswer.model_validate(
            {
                "question_id": 1,
                "question_code": "x",
                "answer_type": "multi_choice",
                "extraction_confidence": 0.9,
                "reasoning": "test",
            }
        )


def test_prompt_contains_only_compact_incremental_context() -> None:
    """上下文包含历史结构化值、摘要和当前对话，不拼接全量原始历史。"""
    prompt = build_user_prompt(
        {
            1: {
                "answer": "青霉素",
                "answer_type": "multiple_choice",
                "selected_option_codes": ["penicillin"],
                "confidence": 0.9,
                "source_turns": ["m1"],
            }
        },
        "用户历史说没有过敏，后续反问得知青霉素过敏；",
        [{"turn": 8, "message_id": "m8", "patient": "是青霉素过敏", "ai_question": "请确认"}],
    )
    assert "青霉素" in prompt
    assert "后续反问得知" in prompt
    assert "m8" in prompt


def test_model_contract_requires_ai_normalized_answer_fields() -> None:
    """模型必须直接给出题目类型、最终值或真实选项编码。"""
    candidate = ExtractionCandidate.model_validate(
        {
            "question_id": 12,
            "answer_type": "text",
            "answer_value": "腹泻3-4次/日",
            "selected_option_codes": [],
            "evidence": "我一天大概拉三四次",
            "confidence": 0.93,
        }
    )

    assert set(candidate.model_dump()) == {
        "question_id",
        "answer_type",
        "answer_value",
        "selected_option_codes",
        "evidence",
        "confidence",
    }
    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate(
            {
                "question_id": 12,
                "answer_type": "text",
                "answer_value": {"raw": "不允许任意对象"},
                "selected_option_codes": [],
                "evidence": "患者原话",
                "confidence": 0.9,
            }
        )


def test_ai_option_code_is_used_without_backend_semantic_mapping() -> None:
    """选择题由 AI 直接返回真实 option_code，后端只验证编码存在。"""
    raw = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 12,
                    "answer_type": "single_choice",
                    "answer_value": None,
                    "selected_option_codes": ["yes"],
                    "evidence": "最近确实有腹泻",
                    "confidence": 0.93,
                }
            ]
        }
    )
    result = FieldExtractionAgent._build_result(
        raw,
        questions=[
            {
                "question_id": 12,
                "question_code": "bowel_change",
                "answer_type": "single_choice",
                "options": [
                    {
                        "option_code": "yes",
                        "option_label": "有",
                        "option_value": "true",
                    },
                    {
                        "option_code": "no",
                        "option_label": "无",
                        "option_value": "false",
                    },
                ],
            }
        ],
        source_message_ids=["MSG-12"],
    )

    assert len(result.extracted_answers) == 1
    answer = result.extracted_answers[0]
    assert answer.question_code == "bowel_change"
    assert answer.answer_type == "single_choice"
    assert answer.selected_option_codes == ["yes"]
    assert answer.source_message_ids == ["MSG-12"]
    assert answer.reasoning == "最近确实有腹泻"


def test_unknown_question_type_falls_back_to_text() -> None:
    """题库中的未知类型回退 text，不再形成护士人工介入。"""
    raw = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 13,
                    "answer_type": "text",
                    "answer_value": "视力模糊",
                    "selected_option_codes": [],
                    "evidence": "最近看东西有点模糊",
                    "confidence": 0.88,
                }
            ]
        }
    )
    result = FieldExtractionAgent._build_result(
        raw,
        questions=[
            {
                "question_id": 13,
                "question_code": "vision_status",
                "answer_type": "unknown_type",
                "options": [],
            }
        ],
        source_message_ids=["MSG-13"],
    )

    assert result.extracted_answers[0].answer_type == "text"
    assert result.extracted_answers[0].answer_value == "视力模糊"
    assert result.invalid_answers == []


def test_prompt_requires_ai_to_return_final_structured_answer() -> None:
    """提示词要求模型完成语义归属和答案规范化，后端不再二次猜测。"""
    prompt = build_system_prompt(
        {"scale_name": "测试量表", "version_code": "v1"},
        [
            {
                "question_id": 12,
                "question_code": "bowel_change",
                "question_text": "排泄情况",
                "answer_type": "text",
                "options": [],
                "required": True,
            }
        ],
    )

    output_section = prompt.split("## 输出格式", maxsplit=1)[1]
    for field in (
        '"question_id"',
        '"answer_type"',
        '"answer_value"',
        '"selected_option_codes"',
        '"evidence"',
        '"confidence"',
    ):
        assert field in output_section
    assert "必须直接返回题目定义中的 option_code" in output_section
    assert "无法明确对应任何题目时返回" in output_section
    assert '"question_code"' not in output_section
    assert '"clinical_score"' not in output_section


def test_choice_label_is_not_guessed_into_option_code() -> None:
    """AI 若返回展示标签而不是真实编码，后端不得再做语义映射。"""
    raw = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 12,
                    "answer_type": "single_choice",
                    "answer_value": None,
                    "selected_option_codes": ["有"],
                    "evidence": "最近确实有腹泻",
                    "confidence": 0.93,
                }
            ]
        }
    )
    result = FieldExtractionAgent._build_result(
        raw,
        questions=[
            {
                "question_id": 12,
                "question_code": "bowel_change",
                "answer_type": "single_choice",
                "options": [
                    {"option_code": "yes", "option_label": "有", "option_value": "true"},
                    {"option_code": "no", "option_label": "无", "option_value": "false"},
                ],
            }
        ],
        source_message_ids=["MSG-12"],
    )

    assert result.extracted_answers == []
    assert result.invalid_answers[0].error == "选择题包含无效 option_code: 有"


def test_boolean_must_be_normalized_by_ai_not_keyword_parser() -> None:
    """布尔题只接受 AI 已规范化的 bool，不接受后端再解析“没有”等自然语言。"""
    question = {
        "question_id": 13,
        "question_code": "allergy",
        "answer_type": "boolean",
        "options": [],
    }
    invalid = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 13,
                    "answer_type": "boolean",
                    "answer_value": "没有",
                    "selected_option_codes": [],
                    "evidence": "没有过敏",
                    "confidence": 0.98,
                }
            ]
        }
    )
    valid = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 13,
                    "answer_type": "boolean",
                    "answer_value": False,
                    "selected_option_codes": [],
                    "evidence": "没有过敏",
                    "confidence": 0.98,
                }
            ]
        }
    )

    invalid_result = FieldExtractionAgent._build_result(
        invalid, questions=[question], source_message_ids=["MSG-13"]
    )
    valid_result = FieldExtractionAgent._build_result(
        valid, questions=[question], source_message_ids=["MSG-13"]
    )

    assert invalid_result.extracted_answers == []
    assert invalid_result.invalid_answers[0].error == "布尔题 answer_value 必须是 bool"
    assert valid_result.extracted_answers[0].answer_value is False


def test_ai_can_leave_turn_unmapped_without_backend_guess() -> None:
    """无法对应题目时 answers 为空，本轮不形成结构化答案。"""
    raw = RawExtractionResult.model_validate({"answers": []})
    result = FieldExtractionAgent._build_result(
        raw,
        questions=[
            {
                "question_id": 1,
                "question_code": "diet",
                "answer_type": "text",
                "options": [],
            }
        ],
        source_message_ids=["MSG-1"],
    )

    assert result.extracted_answers == []
    assert result.invalid_answers == []
    assert result.missing_questions == [1]
