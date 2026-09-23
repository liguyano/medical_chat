"""AI 选择题实际选项分数与未完成量表回归测试。"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.managers.extraction_result_writer import (
    _score_rule_matches,
    recalculate_submission_score,
)


def _query_result(items):
    return SimpleNamespace(all=lambda: list(items))


def _question(question_id, *, required=True):
    return SimpleNamespace(id=question_id, required=required)


def _answer(answer_id, question_id, answer_type="single_choice", score=None):
    return SimpleNamespace(
        id=answer_id,
        question_id=question_id,
        answer_type=answer_type,
        clinical_score=score,
    )


def _option(answer_id, score):
    return SimpleNamespace(
        assessment_answer_id=answer_id,
        clinical_score=score,
    )


def _session(*, required, scored, answers, options=(), rules=()):
    """按重算函数的查询顺序提供内存记录，不连接真实数据库。"""
    db = MagicMock()
    submission = SimpleNamespace(
        total_score=Decimal("99"),
        risk_level="stale_risk",
        result_summary="旧结论",
        updator="old",
    )
    db.get.return_value = submission
    ordered_results = [
        list(required),
        [_question(item) for item in scored],
        list(answers),
    ]
    if any(
        answer.question_id in scored and
        answer.answer_type in {"single_choice", "multiple_choice"}
        for answer in answers
    ):
        ordered_results.append(list(options))
    ordered_results.append(list(rules))
    db.scalars.side_effect = [
        _query_result(rows) for rows in ordered_results
    ]
    return db, submission


def test_selected_home_environment_options_produce_actual_score():
    answers = [_answer(i, i) for i in range(1, 15)]
    # 14 项中 12 项得 1 分、2 项得 0 分。
    options = [_option(i, Decimal(1 if i <= 12 else 0)) for i in range(1, 15)]
    db, submission = _session(
        required=range(1, 15),
        scored=range(1, 15),
        answers=answers,
        options=options,
    )

    scores = recalculate_submission_score(db, 81, 9)

    assert len(scores) == 1
    assert scores[0].score_value == Decimal(12)
    assert submission.total_score == Decimal(12)
    assert submission.risk_level is None  # 不使用跨量表 5/10 分阈值
    assert answers[0].clinical_score == Decimal(1)
    assert answers[-1].clinical_score == Decimal(0)


def test_genuine_zero_score_is_not_treated_as_incomplete():
    answer = _answer(10, 1)
    db, submission = _session(
        required=[1], scored=[1], answers=[answer],
        options=[_option(10, Decimal(0))],
    )
    scores = recalculate_submission_score(db, 11, 3)

    assert len(scores) == 1
    assert scores[0].score_value == Decimal(0)
    assert submission.total_score == Decimal(0)
    assert answer.clinical_score == Decimal(0)


def test_multiple_choice_and_existing_numeric_score_are_added_once():
    answers = [
        _answer(10, 1, "multiple_choice", Decimal(999)),
        _answer(20, 2, "number", Decimal(4)),
    ]
    db, _ = _session(
        required=[1, 2], scored=[1, 2],
        answers=answers,
        options=[_option(10, Decimal(2)), _option(10, Decimal(3))],
    )
    scores = recalculate_submission_score(db, 22, 4)

    assert scores[0].score_value == Decimal(9)  # 2+3+4，不叠加旧的999
    assert answers[0].clinical_score == Decimal(5)
    assert scores[0].calculation_detail == {"question_1": 5.0, "question_2": 4.0}


def test_missing_required_answer_removes_stale_zero_score():
    db, submission = _session(
        required=[1, 2], scored=[1, 2],
        answers=[_answer(10, 1)], options=[_option(10, Decimal(1))],
    )
    scores = recalculate_submission_score(db, 33, 5)

    assert scores == []
    assert submission.total_score is None
    assert submission.result_summary is None
    assert submission.risk_level is None
    db.execute.assert_called_once()


def test_missing_option_score_must_not_become_zero():
    answer = _answer(10, 1)
    db, submission = _session(
        required=[1], scored=[1], answers=[answer], options=[_option(10, None)],
    )
    scores = recalculate_submission_score(db, 44, 6)

    assert scores == []
    assert submission.total_score is None
    assert answer.clinical_score is None


def test_no_scored_items_does_not_create_artificial_total_score():
    db, submission = _session(required=[1], scored=[], answers=[_answer(10, 1)])
    assert recalculate_submission_score(db, 55, 7) == []
    assert submission.total_score is None


def test_scored_but_optional_unanswered_item_does_not_create_partial_total():
    db, submission = _session(
        required=[1], scored=[1, 2], answers=[_answer(10, 1)],
    )
    assert recalculate_submission_score(db, 56, 7) == []
    assert submission.total_score is None


def test_uses_only_scale_specific_interpretation_rule():
    answer = _answer(10, 1)
    rule = SimpleNamespace(
        condition_expression={"expression": "total_score >= 1 and total_score <= 14"},
        result_payload={
            "result": "得分越低，表明居家环境风险越大",
        },
    )
    db, submission = _session(
        required=[1], scored=[1], answers=[answer],
        options=[_option(10, Decimal(1))], rules=[rule],
    )
    scores = recalculate_submission_score(db, 66, 8)

    assert scores[0].score_value == Decimal(1)
    assert submission.result_summary == "得分越低，表明居家环境风险越大"
    assert submission.risk_level is None
    assert _score_rule_matches("total_score >= 1 and total_score <= 14", Decimal(1))
    assert not _score_rule_matches("other_value >= 1", Decimal(1))
