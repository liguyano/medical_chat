"""最终确认答案与历史 AI 计分依据一致性测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.nursing_plan_service import _can_reuse_source_score


def _query(items):
    return SimpleNamespace(all=lambda: list(items))


def _answer(answer_id, question_id, *, text=None):
    return SimpleNamespace(
        id=answer_id,
        question_id=question_id,
        answer_text=text,
        answer_number=None,
        answer_boolean=None,
        answer_date=None,
        answer_time=None,
        answer_datetime=None,
    )


def _fixture(*, nurse_value, ai_label):
    db = MagicMock()
    # 第一条查询为本量表应计分题列表，后四条按两份提交读取题目/选项。
    db.scalars.return_value = _query([101])
    nurse = _answer(501, 101, text=nurse_value)
    ai = _answer(401, 101)
    db.execute.side_effect = [
        _query([(nurse, SimpleNamespace(id=101))]),
        _query([]),
        _query([(ai, SimpleNamespace(id=101))]),
        _query([(401, ai_label)]),
    ]
    return db, SimpleNamespace(id=50), SimpleNamespace(id=40)


def test_matching_final_confirmed_answer_can_reuse_real_ai_option_score():
    db, final, ai = _fixture(nurse_value="是", ai_label="是")
    assert _can_reuse_source_score(db, final, ai, 30)


def test_nurse_changed_scored_answer_blocks_stale_ai_score():
    db, final, ai = _fixture(nurse_value="否", ai_label="是")
    assert not _can_reuse_source_score(db, final, ai, 30)


def test_missing_final_scored_answer_blocks_stale_ai_score():
    db, final, ai = _fixture(nurse_value=None, ai_label="是")
    assert not _can_reuse_source_score(db, final, ai, 30)
