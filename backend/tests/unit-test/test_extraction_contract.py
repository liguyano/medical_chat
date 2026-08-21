"""字段抽取统一契约的纯单元测试。"""

import pytest
from pydantic import ValidationError

from medagent.agents.service_agent.extraction_agent.prompt import build_user_prompt
from medagent.agents.service_agent.extraction_agent.types import normalize_answer_type
from medagent.agents.service_agent.extraction_agent.validator import ExtractedAnswer


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
