"""话题式评估的模型输入契约，不替代真实模型效果评估。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from medagent.agents.service_agent.dialog_agent.prompt import build_system_prompt
from medagent.agents.service_agent.extraction_agent.prompt import (
    build_system_prompt as build_extraction_prompt,
)
from medagent.agents.service_agent.schedule_agent import QuestionTask
from medagent.agents.service_agent.schedule_agent.prompts import (
    DEVIATION_CHECK_SYSTEM_PROMPT,
    TASK_TODO_SYSTEM_PROMPT,
)

from app.services.voice_gateway import VoiceGateway
from app.workers.dialog_agent_runner import DialogAgentRunner


def task():
    return QuestionTask(
        question_id=1,
        question_code="eating",
        question_name="进食",
        patient_text="进食是否需要帮助？",
        question_type="单选",
        required=True,
        sort_no=1,
    )


def test_shared_dialog_policy_keeps_topics_and_evidence_separate():
    prompt = build_system_prompt({}, [task()])
    assert "【生活话题引导】" in prompt
    for rule in ("女儿做饭", "不能据此判断", "时间范围", "固定施测", "拒答", "不虚构"):
        assert rule in prompt
    assert "3至6轮" not in prompt


def test_voice_remaining_prompt_inherits_topic_policy():
    prompt = VoiceGateway._build_remaining_assessment_instructions(
        patient_info={}, remaining_tasks=[task()]
    )
    assert "【生活话题引导】" in prompt
    assert "completed=true" in prompt


@pytest.mark.asyncio
async def test_opening_model_receives_topic_policy():
    class Model:
        async def ainvoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content="先聊聊您今天这顿饭，吃得怎么样？")

    model = Model()
    runner = DialogAgentRunner(
        session_id="topic-test",
        patient_info={},
        scale_codes=[],
        model=model,
        redis_client=SimpleNamespace(),
    )
    await runner._generate_opening_question(task())
    assert "【生活话题引导】" in model.messages[0].content
    assert "进食是否需要帮助" in model.messages[1].content


def test_schedule_allows_related_topic_bridges_without_losing_required_items():
    assert "生活话题" in TASK_TODO_SYSTEM_PROMPT
    assert "话题过渡不算偏离" in DEVIATION_CHECK_SYSTEM_PROMPT
    assert "AI 跳过了必答题，直接询问后面的问题" not in DEVIATION_CHECK_SYSTEM_PROMPT


def test_extraction_requires_patient_evidence_instead_of_topic_assumptions():
    prompt = build_extraction_prompt({}, [])
    assert "女儿做饭" in prompt
    assert "不能推断进食需要喂饭" in prompt
    assert "不能推断当前住院活动能力" in prompt
    assert "患者没有明确回答的目标题保持缺失" in prompt


@pytest.mark.asyncio
async def test_followup_preserves_topic_guidance_and_actual_target(monkeypatch):
    from app.workers import dialog_agent_runner as module
    from app.workers import dialog_agent_runtime as runtime

    engine = SimpleNamespace(update_session=AsyncMock())
    agent = SimpleNamespace(initialize=AsyncMock(), engine=engine)
    monkeypatch.setattr(module, "create_dialog_agent", lambda **kwargs: agent)
    monkeypatch.setattr(
        runtime,
        "get_runtime_dependencies",
        lambda _: dict.fromkeys(["middlewares", "state_store", "history_store", "tool_executor"]),
    )
    monkeypatch.setattr(module.ScheduleTaskStore, "get_guidance", lambda *_: {})
    runner = DialogAgentRunner(
        session_id="topic-test",
        patient_info={},
        scale_codes=[],
        model=SimpleNamespace(),
        redis_client=SimpleNamespace(),
    )
    runner.history = SimpleNamespace(
        get_dialog_history=AsyncMock(return_value=[]), format_for_langchain=lambda _: []
    )
    await runner._build_agent(
        questions=[task()],
        turn_no=2,
        patient_answer="女儿做饭",
        next_question=task(),
        plan_exhausted=False,
        text_delta_sink=AsyncMock(),
    )
    instructions = engine.update_session.call_args.kwargs["instructions"]
    assert "融入患者当前生活话题" in instructions
    assert "量表参考表达：进食是否需要帮助" in instructions
    assert "不主动展开宣教" in instructions
