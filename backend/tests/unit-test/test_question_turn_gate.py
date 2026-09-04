"""选题工具状态机的真实校验回归。"""

from app.services.dialog_question_turn import QuestionTurnSelection


def test_invalid_selection_does_not_close_patient_output():
    turn = QuestionTurnSelection({"candidate_question_ids": [1, 2], "active_question_id": None})
    assert turn.allow_output
    assert turn.report({"selected_question_id": 1, "active_question_id": 1})["success"]
    assert turn.allow_output
    assert not turn.report({"selected_question_id": 9, "active_question_id": 9})["success"]
    assert turn.allow_output
    assert not turn.report({"selected_question_id": 2, "active_question_id": 2})["success"]
    assert turn.allow_output
    assert turn.report({"selected_question_id": 1, "active_question_id": 1})["success"]
    assert turn.allow_output


def test_explicit_empty_selection_allows_natural_reply():
    turn = QuestionTurnSelection({"candidate_question_ids": [], "active_question_id": 1})
    assert turn.report({"selected_question_id": None, "active_question_id": None})["success"]
    assert turn.allow_output
    assert turn.decision == {"selected_question_id": None, "active_question_id": None}


def test_clarifying_active_question_is_not_a_new_selection():
    turn = QuestionTurnSelection({"candidate_question_ids": [2], "active_question_id": 1})
    assert turn.report({"selected_question_id": None, "active_question_id": 1})["success"]
    assert turn.decision == {"selected_question_id": None, "active_question_id": 1}


def test_question_choice_report_is_not_a_patient_business_event(monkeypatch):
    from app.services import tool_interaction_service

    monkeypatch.setattr(tool_interaction_service.model_base, "SessionLocal", None)
    assert (
        tool_interaction_service.publish_tool_result(
            session_no="s",
            task_id=1,
            message_no=None,
            tool_name="report_question_choice",
            tool_args={},
            tool_result={"success": True},
            publisher=None,
        )
        is None
    )
