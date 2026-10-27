"""话题式评估的模型输入契约，不替代真实模型效果评估。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.service_agent.dialog_agent.conversation_scenes import (
    question_conversation_context,
)
from medagent.agents.service_agent.dialog_agent.prompt import (
    allows_topic_intro,
    build_system_prompt,
)
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


def test_topic_policy_requires_interest_first_then_wait():
    prompt = build_system_prompt({}, [task()])
    for rule in (
        "先选话题",
        "喜欢看什么电视",
        "喜欢吃什么",
        "做什么运动",
        "等待患者回答",
        "同一轮",
    ):
        assert rule in prompt


def test_each_response_has_one_short_question_and_no_stage_directions():
    prompt = build_system_prompt({}, [task()])
    for rule in ("一次只问一个实际问题", "最多60字", "患者回答后", "不要把括号", "问完立即停下"):
        assert rule in prompt


def test_effective_prompts_remove_old_questionnaire_examples_and_scripts():
    for prompt in [
        build_system_prompt({}, [task()]),
        VoiceGateway._build_remaining_assessment_instructions({}, [task()]),
        VoiceGateway._build_recovery_question_instructions(
            {}, task(), mode_label="恢复", transition_rule="自然衔接"
        ),
    ]:
        for old in [
            "这顿是自己拿勺吃的，还是有人帮忙",
            "【话术模板】",
            "再自然过渡到下一项护理问题",
            "按 Task-todo 一次只收集一个主题",
        ]:
            assert old not in prompt
        assert "不能把“好”改写为“吃饭没问题”" in prompt


def test_eating_reference_is_a_scene_not_a_bare_ability_question():
    prompt = VoiceGateway._build_remaining_assessment_instructions({}, [task()])
    assert "scene_guidance" in prompt
    assert "餐具" in prompt and "送入口中" in prompt
    assert "喜好或餐具不能证明自理" in prompt
    assert "clinical_reference" in prompt


def test_eating_scene_keeps_clinical_conditions_and_fixed_tests_unchanged():
    feeding = task().model_copy(update={"patient_text": "过去24小时进食是否需要帮助？"})
    context = question_conversation_context(feeding)
    assert context["clinical_reference"] == "过去24小时进食是否需要帮助？"
    fixed = feeding.model_copy(update={"scale_code": "MMSE"})
    assert "scene_guidance" not in question_conversation_context(fixed)


def test_voice_recovery_keeps_eating_scene_and_brief_rules():
    prompt = VoiceGateway._build_recovery_question_instructions(
        {}, task(), mode_label="恢复", transition_rule="自然衔接"
    )
    assert "scene_guidance" in prompt
    assert "一次只问一个实际问题" in prompt


def test_sensation_topic_is_not_mistaken_for_direct_pain_assessment():
    sensation = task().model_copy(
        update={
            "question_name": "感觉",
            "patient_text": "有没有发麻，或冷热、疼痛感觉改变？",
        }
    )
    assert allows_topic_intro(sensation)
    assert not allows_topic_intro(task().model_copy(update={"question_name": "疼痛评分"}))


@pytest.mark.parametrize(
    "name,section,scale",
    [
        ("注意力", None, None),
        ("执行指令", None, None),
        ("画钟", None, None),
        ("呼吸R", None, None),
        ("BP", None, None),
        ("项目一", "认知评估", None),
        ("项目二", None, "MMSE"),
    ],
)
def test_fixed_administration_and_vital_aliases_skip_interest_intro(name, section, scale):
    question = task().model_copy(
        update={"question_name": name, "section_name": section, "scale_code": scale}
    )
    assert not allows_topic_intro(question)


@pytest.mark.parametrize("answered,expected", [(set(), 1), ({1}, 2)])
def test_topic_intro_keeps_unanswered_target_then_skips_real_answers(answered, expected):
    second = task().model_copy(update={"question_id": 2, "question_code": "walking"})
    selected, exhausted = DialogAgentRunner._select_unanswered_question(
        questions=[task(), second],
        current_index=0,
        answered_question_ids=answered,
        prefer_current=True,
    )
    assert selected.question_id == expected
    assert exhausted is False


def test_voice_remaining_prompt_inherits_topic_policy():
    prompt = VoiceGateway._build_remaining_assessment_instructions(
        patient_info={}, remaining_tasks=[task()]
    )
    assert "【生活话题引导】" in prompt
    assert "completed=true" in prompt
    assert "先选话题" in prompt
    assert "等待患者回答" in prompt


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
@pytest.mark.parametrize("introduced", [False, True])
async def test_followup_preserves_topic_guidance_and_actual_target(monkeypatch, introduced):
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
        get_dialog_history=AsyncMock(
            return_value=[
                SimpleNamespace(
                    related_question_id=1,
                    intent_type="话题引入",
                )
            ]
            if introduced
            else []
        ),
        format_for_langchain=lambda _: [],
    )
    await runner._build_agent(
        questions=[task()],
        turn_no=2,
        patient_answer="女儿做饭",
        next_question=task(),
        plan_exhausted=False,
        text_delta_sink=AsyncMock(),
        introduce_topic=True,
    )
    instructions = engine.update_session.call_args.kwargs["instructions"]
    assert ("本轮阶段：话题展开" if introduced else "本轮阶段：话题引入") in instructions
    assert agent.topic_intro is (not introduced)
    assert "clinical_reference" in instructions and "进食是否需要帮助" in instructions
    assert "不主动展开宣教" in instructions


@pytest.mark.asyncio
async def test_answer_after_intro_expands_same_target_in_real_runner():
    runner = DialogAgentRunner(
        session_id="topic-test",
        patient_info={},
        scale_codes=[],
        model=SimpleNamespace(),
        redis_client=SimpleNamespace(),
    )
    first = task()
    second = task().model_copy(update={"question_id": 2})
    runner._load_patient_message = Mock(
        return_value=SimpleNamespace(
            turn_no=2,
            content_text="喜欢吃面条",
            asr_text=None,
        )
    )
    runner._find_ai_message = Mock(
        side_effect=lambda *, turn_no: (
            SimpleNamespace(
                related_question_id=1,
                intent_type="话题引入",
            )
            if turn_no == 2
            else None
        )
    )

    def select(*, current_index, questions, prefer_current=False):
        return runner._select_unanswered_question(
            questions=questions,
            current_index=current_index,
            answered_question_ids=set(),
            prefer_current=prefer_current,
        )

    async def plan(**kwargs):
        question, exhausted = select(
            current_index=kwargs["current_index"],
            questions=kwargs["questions"],
            prefer_current=True,
        )
        return question, exhausted, None

    runner._plan_topic_turn = AsyncMock(side_effect=plan)
    agent = SimpleNamespace(
        handle_patient_input=AsyncMock(return_value="这顿面条是自己拿筷子吃的吗？"),
        close=AsyncMock(),
        topic_intro=False,
    )
    runner._build_agent = AsyncMock(return_value=agent)
    runner._start_generation = Mock(return_value="1-0")
    runner._persist_completed_question = AsyncMock(
        return_value=(SimpleNamespace(message_no="ai3"), "2-0")
    )
    runner.output_store = SimpleNamespace(complete=Mock())
    runner._save_state = Mock()
    result = await runner._run_answer(
        questions=[first, second],
        state={"current_question_index": 0},
        source_message_id="patient2",
        source_event_id="0-1",
    )
    assert result["status"] == "turn_completed"
    assert runner._build_agent.call_args.kwargs["next_question"].question_id == 1
    assert runner._build_agent.call_args.kwargs["introduce_topic"] is False
    assert runner._persist_completed_question.call_args.kwargs["introduce_topic"] is False
