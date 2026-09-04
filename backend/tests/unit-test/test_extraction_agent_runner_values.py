"""Extraction Agent 有效答案边界测试。"""

from types import SimpleNamespace

from app.workers.extraction_agent_runner import ExtractionAgentRunner


def _answer(value=None, options=None, confidence=0.9):
    return SimpleNamespace(
        answer_value=value,
        selected_option_codes=options or [],
        extraction_confidence=confidence,
    )


def test_empty_extraction_is_not_persistable():
    """None、空字符串和纯空白不得创建结构化答案。"""
    assert ExtractionAgentRunner._has_extracted_value(_answer()) is False
    assert ExtractionAgentRunner._has_extracted_value(_answer("")) is False
    assert ExtractionAgentRunner._has_extracted_value(_answer("   ")) is False


def test_false_zero_and_selected_option_are_persistable():
    """布尔 False、数值 0 和有效选项都是合法答案。"""
    assert ExtractionAgentRunner._has_extracted_value(_answer(False)) is True
    assert ExtractionAgentRunner._has_extracted_value(_answer(0)) is True
    assert (
        ExtractionAgentRunner._has_extracted_value(
            _answer(None, ["smoking_no"])
        )
        is True
    )


def test_low_confidence_ai_mapping_is_not_persistable():
    """AI 自己也不确定的映射不写入结构化答案。"""
    assert (
        ExtractionAgentRunner._is_persistable_answer(
            _answer("可能吧", confidence=0.59)
        )
        is False
    )
    assert (
        ExtractionAgentRunner._is_persistable_answer(
            _answer("明确回答", confidence=0.6)
        )
        is True
    )
