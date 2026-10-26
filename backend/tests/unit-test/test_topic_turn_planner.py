"""连续话题规划的剩余题边界与通话确认回归。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.service_agent.dialog_agent.topic_planner import plan_topic_turn
from medagent.agents.service_agent.schedule_agent import QuestionTask


def task(i, name):
    return QuestionTask(
        question_id=i,
        question_code=f"q{i}",
        question_name=name,
        patient_text=name,
        question_type="文本",
        required=True,
        sort_no=i,
    )


class Model:
    def __init__(self, target):
        self.target = target
        self.calls = []

    def bind(self, **kwargs):
        self.options = kwargs
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(
            content=json.dumps(
                {
                    "question_id": self.target,
                    "topic": "散步回来休息",
                    "transition": "从散步回家坐下再起身聊起",
                    "mode": "continue",
                },
                ensure_ascii=False,
            )
        )


@pytest.mark.asyncio
async def test_related_gap_can_be_selected_out_of_order():
    model = Model(3)
    plan = await plan_topic_turn(
        model,
        [task(2, "进食"), task(3, "起身")],
        [{"role": "user", "content": "散步回来会坐一会儿"}],
        "散步回来会坐一会儿",
    )
    assert plan.question_id == 3
    assert model.options["extra_body"]["enable_thinking"] is False
    assert "散步回来" in str(model.calls[0])


@pytest.mark.asyncio
async def test_answered_or_invented_target_is_rejected():
    with pytest.raises(ValueError, match="剩余"):
        await plan_topic_turn(Model(99), [task(2, "进食")], [], "喜欢散步")


@pytest.mark.asyncio
async def test_hearing_check_does_not_start_new_assessment_or_call_planner():
    model = Model(2)
    plan = await plan_topic_turn(model, [task(2, "进食")], [], "嗯，听得到我说话吗？")
    assert plan.mode == "communication"
    assert model.calls == []


@pytest.mark.asyncio
async def test_hearing_check_with_symptoms_is_not_swallowed():
    model = Model(2)
    plan = await plan_topic_turn(model, [task(2, "当前不适")], [], "听得到吗，我胸口很不舒服")
    assert plan.mode != "communication"
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_runner_plans_from_database_gaps_and_persisted_history():
    from app.workers.dialog_agent_runner import DialogAgentRunner

    runner = DialogAgentRunner(
        session_id="topic-test",
        patient_info={},
        scale_codes=[],
        model=Model(3),
        redis_client=SimpleNamespace(),
    )
    questions = [task(1, "已经回答"), task(2, "进食"), task(3, "起身")]
    runner._remaining_questions = Mock(return_value=questions[1:])
    runner.history = SimpleNamespace(
        get_dialog_history=AsyncMock(return_value=[{"role": "user", "content": "散步回来坐下"}]),
        format_for_langchain=lambda history: history,
    )
    target, exhausted, plan = await runner._plan_topic_turn(
        questions=questions, current_index=0, patient_answer="散步回来坐下"
    )
    assert target.question_id == 3 and not exhausted
    assert plan.mode == "continue"
