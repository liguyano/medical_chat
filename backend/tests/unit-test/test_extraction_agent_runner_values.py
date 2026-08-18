"""Extraction Agent 有效答案边界测试。"""

from types import SimpleNamespace

from app.workers.extraction_agent_runner import ExtractionAgentRunner


def _answer(value=None, options=None):
    return SimpleNamespace(
        answer_value=value,
        selected_option_codes=options or [],
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
