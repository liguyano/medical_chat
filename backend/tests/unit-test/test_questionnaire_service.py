"""传统问卷服务的纯逻辑测试。"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.errors.handlers import AppError
from app.services.questionnaire_service import (
    _parse_value,
    _score_expression_matches,
    _status,
)


def _question(question_type: str, **kwargs):
    values = {
        "question_type": question_type,
        "question_name": "测试题",
        "validation_rule": None,
        "value_precision": None,
        "derived": False,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _option(code: str, score: str = "0"):
    return SimpleNamespace(
        option_code=code,
        option_label=f"选项 {code}",
        clinical_score=Decimal(score),
    )


def test_parse_questionnaire_values_and_scores():
    options = {"yes": _option("yes", "2"), "no": _option("no", "0")}

    single = _parse_value(_question("single_choice"), "yes", options)
    assert single["answer_type"] == "single_choice"
    assert single["selected_options"][0].option_code == "yes"
    assert single["clinical_score"] == Decimal(2)

    multiple = _parse_value(
        _question("multiple_choice"),
        ["yes", "no"],
        options,
    )
    assert multiple["answer_type"] == "multiple_choice"
    assert multiple["clinical_score"] == Decimal(2)

    assert _parse_value(_question("boolean"), False, {})["answer_boolean"] is False
    assert _parse_value(_question("number"), "12.5", {})["answer_number"] == Decimal(
        "12.5"
    )


def test_parse_questionnaire_rejects_invalid_values_and_empty_values():
    with pytest.raises(AppError, match="选项无效"):
        _parse_value(_question("single_choice"), "unknown", {"yes": _option("yes")})

    with pytest.raises(AppError, match="有效数字"):
        _parse_value(_question("number"), "not-a-number", {})

    with pytest.raises(AppError, match="选项无效"):
        _parse_value(
            _question("multiple_choice"),
            ["yes", "yes"],
            {"yes": _option("yes")},
        )

    with pytest.raises(AppError, match="需要选择是或否"):
        _parse_value(_question("boolean"), ["是"], {})

    assert _parse_value(_question("text"), "", {}) is None
    assert _parse_value(_question("multiple_choice"), [], {}) is None


def test_score_expression_supports_threshold_ranges():
    assert _score_expression_matches(
        "total_score >= 3 and total_score < 8",
        Decimal(5),
    )
    assert not _score_expression_matches("total_score >= 3", Decimal(2))
    assert not _score_expression_matches("patient_age > 18", Decimal(5))


def test_number_precision_and_text_length_are_validated():
    with pytest.raises(AppError, match="最多保留"):
        _parse_value(
            _question("number", value_precision=1),
            "1.23",
            {},
        )
    with pytest.raises(AppError, match="内容过长"):
        _parse_value(
            _question("text", validation_rule={"maxLength": 2}),
            "超过两字",
            {},
        )


def test_questionnaire_status_distinguishes_draft_return_and_confirmation():
    draft = SimpleNamespace(
        submission_status="in_progress",
        answered_question_count=1,
    )
    submitted = SimpleNamespace(
        submission_status="submitted",
        answered_question_count=2,
    )

    assert _status(SimpleNamespace(task_status="pending"), {}) == "not_started"
    assert _status(SimpleNamespace(task_status="in_progress"), {1: draft}) == "in_progress"
    assert _status(SimpleNamespace(task_status="in_progress"), {1: submitted}) == "returned"
    assert _status(SimpleNamespace(task_status="pending_review"), {1: submitted}) == "submitted"
    assert _status(SimpleNamespace(task_status="completed"), {1: submitted}) == "confirmed"
