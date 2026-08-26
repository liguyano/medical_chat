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


def test_model_contract_contains_only_minimal_candidate_fields() -> None:
    """模型候选只携带题号、值、原话依据和置信度。"""
    candidate = ExtractionCandidate.model_validate(
        {
            "question_id": 12,
            "value": "腹泻3-4次/日",
            "evidence": "我一天大概拉三四次",
            "confidence": 0.93,
        }
    )

    assert set(candidate.model_dump()) == {
        "question_id",
        "value",
        "evidence",
        "confidence",
    }
    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate(
            {
                "question_id": 12,
                "value": {"raw": "不允许任意对象"},
                "evidence": "患者原话",
                "confidence": 0.9,
            }
        )


def test_minimal_candidate_is_enriched_from_question_definition() -> None:
    """题目编码、类型、来源消息和选项编码均由后端题库事实补齐。"""
    raw = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 12,
                    "value": "有",
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
                    "value": "视力模糊",
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


def test_prompt_requests_minimal_output_instead_of_database_metadata() -> None:
    """提示词不得再要求模型重复生成题目编码、答案类型和临床得分。"""
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

    assert '"question_id"' in prompt
    assert '"value"' in prompt
    assert '"evidence"' in prompt
    assert '"confidence"' in prompt
    output_section = prompt.split("## 输出格式", maxsplit=1)[1]
    assert '"question_code"' not in output_section
    assert '"answer_type"' not in output_section
    assert '"clinical_score"' not in output_section
