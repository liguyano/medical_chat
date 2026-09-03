"""可空选题协议与患者可见输出门禁回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers.dialog_agent_runner import DialogAgentRunner


def test_historical_unlinked_ai_message_does_not_crash_turn_resolution():
    runner = DialogAgentRunner(
        session_id="S",
        patient_info={},
        scale_codes=[],
        model=SimpleNamespace(),
        redis_client=SimpleNamespace(),
    )
    runner._find_ai_message = lambda **_: SimpleNamespace(related_question_id=None)
    assert runner._resolve_current_question_index(SimpleNamespace(turn_no=1), []) is None


def test_question_choice_tool_requires_explicit_nullable_fields():
    from medagent.agents.service_agent.dialog_agent.question_choice import QUESTION_CHOICE_TOOL

    parameters = QUESTION_CHOICE_TOOL["function"]["parameters"]
    assert set(parameters["required"]) == {"selected_question_id", "active_question_id"}
    assert any(
        item.get("type") == "null"
        for item in parameters["properties"]["selected_question_id"]["anyOf"]
    )


def test_choice_prompt_only_exposes_candidates_and_active_question():
    from app.services.dialog_question_turn import build_question_turn_prompt

    context = {
        "candidate_question_ids": [2],
        "active_question_id": 1,
        "questions": [
            {"question_id": 1, "question_text": "当前问题", "status": "asked"},
            {"question_id": 2, "question_text": "可选问题", "status": "unasked"},
            {"question_id": 3, "question_text": "冷却中的问题", "status": "asked"},
        ],
        "recorded_answers": [],
        "current": 0,
        "total": 3,
    }
    prompt = build_question_turn_prompt(context)
    assert "当前问题" in prompt and "可选问题" in prompt
    assert "冷却中的问题" not in prompt
    assert "null" in prompt and "report_question_choice" in prompt


def test_missing_question_choice_cannot_release_text():
    from app.services.dialog_question_turn import QuestionTurnSelection

    turn = QuestionTurnSelection({"candidate_question_ids": [], "active_question_id": None})
    assert turn.allow_output is False
    with pytest.raises(RuntimeError, match="选题"):
        turn.require_decision()


@pytest.fixture
def runner_harness(monkeypatch):
    """替换网络、数据库边界，执行真实 Runner 选题和持久化编排。"""
    from app.models import base as model_base
    from app.services import dialog_question_service

    runner = DialogAgentRunner(
        session_id="S",
        patient_info={},
        scale_codes=[],
        model=SimpleNamespace(),
        redis_client=SimpleNamespace(),
    )
    runner._load_patient_message = lambda _: SimpleNamespace(
        turn_no=1, content_text="您好", asr_text=None
    )
    runner._find_ai_message = lambda **_: None
    runner._load_question_context = lambda _: {
        "candidate_question_ids": [2],
        "active_question_id": 1,
        "questions": [],
        "recorded_answers": [],
    }
    runner._start_generation = MagicMock(return_value="start")
    runner._publish_text_delta = MagicMock()
    runner._save_state = MagicMock()
    runner._mark_generation_failed = MagicMock()
    runner._activate_session = MagicMock()
    runner._ensure_completed_snapshot = MagicMock()
    runner.output_store = MagicMock()
    runner.publisher = MagicMock()
    saved = []
    recorded = []

    async def save_message(_session, **kwargs):
        saved.append(kwargs)
        return SimpleNamespace(**kwargs)

    runner.history.save_message = save_message
    monkeypatch.setattr(model_base, "SessionLocal", MagicMock())
    monkeypatch.setattr(
        dialog_question_service, "record_question_turn", lambda *args: recorded.append(args)
    )
    return runner, saved, recorded


def install_agent(runner, decision):
    async def build(**kwargs):
        async def handle(*args, **metadata):
            await kwargs["text_delta_sink"]("工具前旁白", {})
            if decision is not None:
                assert kwargs["turn_selection"].report(decision)["success"]
            await kwargs["text_delta_sink"]("您好，我会继续协助您。", {})
            return "您好，我会继续协助您。"

        return SimpleNamespace(handle_patient_input=handle, close=AsyncMock())

    runner._build_agent = build


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision",
    [
        {"selected_question_id": None, "active_question_id": None},
        {"selected_question_id": None, "active_question_id": 1},
        {"selected_question_id": 2, "active_question_id": 2},
    ],
)
async def test_answer_persists_actual_choice_even_when_plan_missing(runner_harness, decision):
    runner, saved, recorded = runner_harness
    install_agent(runner, decision)
    result = await runner._run_answer(
        questions=[], state={}, source_message_id="p1", source_event_id=None
    )
    assert result["status"] == "turn_completed"
    assert saved[0]["related_question_id"] == decision["active_question_id"]
    assert saved[0]["content_text"] == "您好，我会继续协助您。"
    assert recorded[0][-2:] == (decision["selected_question_id"], decision["active_question_id"])
    event = runner.publisher.publish.call_args.args[0]
    assert event.question_id == (
        str(decision["active_question_id"]) if decision["active_question_id"] is not None else None
    )


@pytest.mark.asyncio
async def test_answer_without_report_never_publishes_text(runner_harness):
    runner, saved, recorded = runner_harness
    install_agent(runner, None)
    with pytest.raises(RuntimeError, match="选题"):
        await runner._run_answer(
            questions=[], state={}, source_message_id="p1", source_event_id=None
        )
    assert not saved and not recorded
    runner._publish_text_delta.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intent,related,selected", [("回应", None, None), ("澄清", 1, None), ("提问", 2, 2)]
)
async def test_answer_retry_repairs_event_before_publishing_snapshot(
    runner_harness, intent, related, selected
):
    runner, saved, recorded = runner_harness
    message = SimpleNamespace(
        turn_no=2, message_no="a1", related_question_id=related, intent_type=intent
    )
    runner._find_ai_message = lambda **_: message

    def ensure(**_):
        assert recorded, "必须先修复事件再恢复完成快照"

    runner._ensure_completed_snapshot = ensure
    result = await runner._run_answer(
        questions=[], state={}, source_message_id="p1", source_event_id=None
    )
    assert result["status"] == "already_completed"
    assert recorded[0][-4:] == ("a1", "p1", selected, related)
    assert not saved


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision",
    [
        {"selected_question_id": None, "active_question_id": None},
        {"selected_question_id": 2, "active_question_id": 2},
    ],
)
async def test_opening_uses_shared_choice_and_activates_even_without_question(
    runner_harness, decision
):
    runner, saved, recorded = runner_harness
    install_agent(runner, decision)
    result = await runner._run_opening(questions=[], state={})
    assert result["status"] == "opening_completed"
    assert saved[0]["related_question_id"] == decision["active_question_id"]
    assert len(saved) == 1 and saved[0]["role_type"] == "AI"
    assert recorded[0][-3:] == (
        None,
        decision["selected_question_id"],
        decision["active_question_id"],
    )
    runner._activate_session.assert_called_once()


@pytest.mark.asyncio
async def test_opening_without_report_does_not_activate_or_publish_text(runner_harness):
    runner, saved, recorded = runner_harness
    install_agent(runner, None)
    with pytest.raises(RuntimeError, match="选题"):
        await runner._run_opening(questions=[], state={})
    assert not saved and not recorded
    runner._activate_session.assert_not_called()
    runner._publish_text_delta.assert_not_called()


@pytest.mark.asyncio
async def test_opening_retry_repairs_event_and_activates_pending_session(runner_harness):
    runner, saved, recorded = runner_harness
    runner._find_ai_message = lambda **_: SimpleNamespace(
        turn_no=1,
        message_no="opening",
        related_question_id=None,
        intent_type="回应",
        content_text="您好",
    )
    result = await runner._run_opening(questions=[], state={})
    assert result["status"] == "already_completed"
    assert recorded[0][-4:] == ("opening", None, None, None)
    assert not saved
    runner._activate_session.assert_called_once()
