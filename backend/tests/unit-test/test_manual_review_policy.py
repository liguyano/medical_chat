from types import SimpleNamespace


def test_fixed_manual_review_codes_are_deterministic():
    from app.services.manual_review_service import (
        FIXED_MANUAL_REVIEW_QUESTION_CODES,
        is_fixed_manual_review_question,
    )

    assert FIXED_MANUAL_REVIEW_QUESTION_CODES == frozenset(
        {"outdoor_night_lighting", "indoor_stair_handrails"}
    )
    assert is_fixed_manual_review_question("outdoor_night_lighting")
    assert is_fixed_manual_review_question("indoor_stair_handrails")
    assert not is_fixed_manual_review_question("bathroom_grab_bars")


def test_manual_review_questions_count_as_processed_but_never_remaining():
    from app.services.manual_review_service import build_manual_review_progress

    snapshot = build_manual_review_progress(
        required_questions=[
            (101, "passage_clear"),
            (102, "outdoor_night_lighting"),
            (103, "indoor_stair_handrails"),
        ],
        answered_question_ids={101},
    )

    assert snapshot.total == 3
    assert snapshot.current == 3
    assert snapshot.completed is True
    assert snapshot.ai_required_question_ids == (101,)
    assert snapshot.manual_review_question_ids == (102, 103)
    assert snapshot.manual_review_pending_question_ids == (102, 103)
    assert snapshot.remaining_question_ids == ()


def test_manual_review_questions_are_filtered_out_of_ai_task_list():
    from app.services.manual_review_service import filter_ai_question_tasks

    tasks = [
        SimpleNamespace(question_code="passage_clear"),
        SimpleNamespace(question_code="outdoor_night_lighting"),
        SimpleNamespace(question_code="indoor_stair_handrails"),
    ]

    filtered = filter_ai_question_tasks(tasks)

    assert [item.question_code for item in filtered] == ["passage_clear"]
