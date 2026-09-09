from types import SimpleNamespace

import pytest

import app.services.voice_turn_guard as guard_module
from app.services.assessment_progress_service import AssessmentProgress
from app.services.voice_turn_guard import VoiceTurnGuard


def test_closing_intent_requires_explicit_end_semantics():
    assert VoiceTurnGuard.has_closing_intent("感谢您的配合，本次评估已完成。")
    assert VoiceTurnGuard.has_closing_intent("好的，我们今天就到这里。")
    assert VoiceTurnGuard.has_closing_intent("这些问题都问完了，谢谢您。")


def test_closing_intent_does_not_treat_polite_or_negative_text_as_end():
    assert not VoiceTurnGuard.has_closing_intent("谢谢您的配合，我们继续下一项。")
    assert not VoiceTurnGuard.has_closing_intent("评估还没有完成，还需要确认一个问题。")
    assert not VoiceTurnGuard.has_closing_intent("感谢您刚才的回答。")


def test_extraction_processed_reads_current_turn_checkpoint():
    redis = SimpleNamespace(
        get=lambda key: {
            "processed_message_ids": ["MSG-1", "MSG-2"]
        }
        if key == "extraction_agent:state:SESS"
        else None
    )
    assert VoiceTurnGuard.extraction_processed(redis, "SESS", "MSG-2")
    assert not VoiceTurnGuard.extraction_processed(redis, "SESS", "MSG-3")
    assert VoiceTurnGuard.extraction_processed(redis, "SESS", None)


def test_recovery_decision_selects_only_first_remaining_task(monkeypatch):
    progress = AssessmentProgress(
        current=2,
        total=4,
        completed=False,
        answered_question_ids=frozenset({1, 2}),
        remaining_question_ids=(3, 4),
    )

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        guard_module.model_base,
        "SessionLocal",
        lambda: FakeDb(),
    )
    monkeypatch.setattr(
        guard_module,
        "refresh_assessment_progress",
        lambda _db, _session_no: progress,
    )
    tasks = [
        SimpleNamespace(question_id=1),
        SimpleNamespace(question_id=4),
        SimpleNamespace(question_id=3),
    ]

    decision = VoiceTurnGuard.build_recovery_decision("SESS", tasks)

    assert decision.should_recover
    assert decision.next_question.question_id == 4


def test_recovery_decision_does_not_recover_completed_assessment(monkeypatch):
    progress = AssessmentProgress(
        current=4,
        total=4,
        completed=True,
        answered_question_ids=frozenset({1, 2, 3, 4}),
        remaining_question_ids=(),
    )

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        guard_module.model_base,
        "SessionLocal",
        lambda: FakeDb(),
    )
    monkeypatch.setattr(
        guard_module,
        "refresh_assessment_progress",
        lambda _db, _session_no: progress,
    )

    decision = VoiceTurnGuard.build_recovery_decision(
        "SESS",
        [SimpleNamespace(question_id=1)],
    )

    assert not decision.should_recover
    assert decision.next_question is None
