"""末尾待确认题的对话推进回归测试。"""

from app.services.dialog_question_turn import QuestionTurnSelection, build_question_turn_prompt


def test_idle_null_is_rejected_when_candidates_are_available():
    """已有可问题且没有当前题时，不能连续用 null/null 进入泛聊死循环。"""
    turn = QuestionTurnSelection(
        {
            "candidate_question_ids": [23, 24],
            "active_question_id": None,
        }
    )

    rejected = turn.report(
        {"selected_question_id": None, "active_question_id": None}
    )

    assert rejected["success"] is False
    assert rejected["retry_selection"] is True
    assert turn.allow_output is False

    accepted = turn.report(
        {"selected_question_id": 23, "active_question_id": 23}
    )
    assert accepted["success"] is True
    assert turn.require_decision() == {
        "selected_question_id": 23,
        "active_question_id": 23,
    }


def test_idle_null_remains_valid_when_no_candidate_is_available():
    """冷却期间没有候选时仍允许自然回应，不伪造题目。"""
    turn = QuestionTurnSelection(
        {"candidate_question_ids": [], "active_question_id": None}
    )

    assert turn.report(
        {"selected_question_id": None, "active_question_id": None}
    )["success"]


def test_prompt_tells_model_to_resume_candidate_after_idle_turn():
    """候选重新出现后明确要求恢复评估，不继续泛化追问。"""
    prompt = build_question_turn_prompt(
        {
            "candidate_question_ids": [23],
            "active_question_id": None,
            "questions": [
                {
                    "question_id": 23,
                    "question_text": "BMI<18.5kg/m²",
                    "status": "asked",
                }
            ],
            "recorded_answers": [],
            "current": 23,
            "total": 25,
        }
    )

    assert "候选非空" in prompt
    assert "null/null" in prompt
    assert "继续完成评估" in prompt
