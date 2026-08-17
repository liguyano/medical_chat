"""Schedule Agent 核心逻辑单元测试。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from medagent.agents.service_agent.schedule_agent import (
    QuestionOption,
    QuestionTask,
    ScheduleAgent,
)


def make_question(code: str, text: str, sort_no: int = 1) -> QuestionTask:
    """创建最小问题任务。"""
    return QuestionTask(
        question_id=sort_no,
        question_code=code,
        question_name=text,
        patient_text=text,
        question_type="单选",
        required=True,
        sort_no=sort_no,
        scale_code="test_scale",
        options=[
            QuestionOption(
                option_code="yes",
                option_label="是",
                option_value="yes",
            )
        ],
    )


def make_llm(payload: dict | str | None = None, *, error: Exception | None = None):
    """创建 OpenAI 兼容客户端替身。"""
    create = AsyncMock()
    if error is not None:
        create.side_effect = error
    else:
        content = (
            json.dumps(payload, ensure_ascii=False)
            if isinstance(payload, dict)
            else payload
        )
        create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def make_agent(
    payload: dict | str | None = None,
    *,
    check_interval: int = 5,
    questions: list[QuestionTask] | None = None,
):
    """创建测试智能体和客户端。"""
    llm = make_llm(
        payload
        or {
            "is_deviation": False,
            "reason": "",
            "completed_questions": [],
            "current_focus": "",
            "suggested_action": "",
        }
    )
    agent = ScheduleAgent(
        "session-1",
        (
            questions
            if questions is not None
            else [
                make_question("smoking", "您是否吸烟？", 1),
                make_question("drinking", "您是否饮酒？", 2),
            ]
        ),
        llm,
        model="qwen-plus",
        check_interval=check_interval,
        max_tokens=512,
    )
    return agent, llm


def test_check_interval_must_be_positive():
    """检查间隔必须为正整数。"""
    with pytest.raises(ValueError, match="check_interval"):
        ScheduleAgent(
            "session",
            [],
            make_llm({}),
            model="qwen-plus",
            check_interval=0,
        )


@pytest.mark.asyncio
async def test_only_fifth_turn_calls_llm():
    """默认每5轮只调用一次模型。"""
    agent, llm = make_agent()
    for _ in range(4):
        result = await agent.evaluate([])
        assert result.checked is False
    result = await agent.evaluate([])
    assert result.checked is True
    llm.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_completion_updates_progress_and_next_question():
    """结构化结果应更新进度并返回下一个问题文本。"""
    agent, _ = make_agent(
        {
            "is_deviation": False,
            "reason": "正常",
            "completed_questions": ["smoking"],
            "current_focus": "吸烟评估",
            "suggested_action": "",
        }
    )
    result = await agent.evaluate([], force=True)
    assert result.completed_questions == ["smoking"]
    assert result.remaining_questions == ["drinking"]
    assert result.next_suggested_question == "您是否饮酒？"
    assert result.progress_percentage == 50.0


@pytest.mark.asyncio
async def test_completed_progress_accumulates_across_checks():
    """不同检查轮次识别的已完成问题应累积。"""
    agent, llm = make_agent(
        {
            "completed_questions": ["smoking"],
            "is_deviation": False,
        }
    )
    await agent.evaluate([], force=True)
    llm.chat.completions.create.return_value.choices[0].message.content = json.dumps(
        {"completed_questions": ["drinking"], "is_deviation": False}
    )
    result = await agent.evaluate([], force=True)
    assert result.completed_questions == ["smoking", "drinking"]
    assert result.remaining_questions == []
    assert result.progress_percentage == 100.0


@pytest.mark.asyncio
async def test_unknown_completed_code_is_ignored():
    """模型不得凭空完成当前量表不存在的问题。"""
    agent, _ = make_agent(
        {"completed_questions": ["unknown"], "is_deviation": False}
    )
    result = await agent.evaluate([], force=True)
    assert result.completed_questions == []


@pytest.mark.asyncio
async def test_malformed_llm_response_fails_open(caplog):
    """非 JSON 响应应记录错误并安全放行。"""
    agent, _ = make_agent("not-json")
    result = await agent.evaluate([], force=True)
    assert result.is_deviation is False
    assert "结构化响应解析失败" in caplog.text


@pytest.mark.asyncio
async def test_llm_exception_fails_open(caplog):
    """模型异常不应中断对话主链路。"""
    llm = make_llm(error=TimeoutError("timeout"))
    agent = ScheduleAgent(
        "session",
        [make_question("smoking", "您是否吸烟？")],
        llm,
        model="qwen-plus",
        check_interval=1,
    )
    result = await agent.evaluate([])
    assert result.is_deviation is False
    assert "LLM 调用失败" in caplog.text


@pytest.mark.asyncio
async def test_missing_tobacco_education_tool_creates_constraint():
    """吸烟特征未调用宣教工具时必须约束下一轮。"""
    agent, _ = make_agent()
    result = await agent.evaluate(
        [{"role": "user", "content": "我每天吸烟十支"}],
        force=True,
    )
    assert result.is_deviation is True
    assert result.missing_tool_calls == [
        "get_education_material(category='tobacco')"
    ]
    assert "戒烟宣教工具" in result.constraint_prompt


@pytest.mark.asyncio
async def test_matching_tobacco_tool_satisfies_requirement():
    """工具名和参数都正确时不应误报。"""
    agent, _ = make_agent()
    result = await agent.evaluate(
        [{"role": "user", "content": "我吸烟"}],
        tool_calls=[
            {
                "name": "get_education_material",
                "arguments": {"category": "tobacco"},
            }
        ],
        force=True,
    )
    assert result.missing_tool_calls == []
    assert result.is_deviation is False


@pytest.mark.asyncio
async def test_wrong_tool_arguments_do_not_satisfy_requirement():
    """只调用同名工具但参数错误仍视为遗漏。"""
    agent, _ = make_agent()
    result = await agent.evaluate(
        [{"role": "user", "content": "我吸烟"}],
        tool_calls=[
            {
                "name": "get_education_material",
                "arguments": {"category": "alcohol"},
            }
        ],
        force=True,
    )
    assert len(result.missing_tool_calls) == 1


@pytest.mark.asyncio
async def test_malformed_tool_record_does_not_break_dialog(caplog):
    """损坏工具记录应被忽略，不得中断患者对话。"""
    agent, _ = make_agent()
    result = await agent.evaluate(
        [{"role": "user", "content": "我吸烟"}],
        tool_calls=[{"arguments": {"category": "tobacco"}}],
        force=True,
    )
    assert result.is_deviation is True
    assert "忽略无效工具调用记录" in caplog.text


@pytest.mark.asyncio
async def test_alias_keywords_do_not_duplicate_missing_tool():
    """同一需求的同义关键词只能生成一条遗漏记录。"""
    agent, _ = make_agent()
    result = await agent.evaluate(
        [{"role": "user", "content": "我抽烟，也有吸烟史"}],
        force=True,
    )
    assert result.missing_tool_calls.count(
        "get_education_material(category='tobacco')"
    ) == 1


@pytest.mark.asyncio
async def test_negated_smoking_does_not_trigger_education_tool():
    """明确否认吸烟时不得误触发戒烟宣教。"""
    agent, _ = make_agent()
    result = await agent.evaluate(
        [{"role": "user", "content": "我不吸烟，也从来不抽烟"}],
        force=True,
    )
    assert result.missing_tool_calls == []


@pytest.mark.asyncio
async def test_llm_suggested_action_is_used_for_deviation():
    """偏离时优先采用模型给出的具体引导动作。"""
    agent, _ = make_agent(
        {
            "is_deviation": True,
            "reason": "持续讨论食堂",
            "completed_questions": [],
            "suggested_action": "简短回答后，请患者继续回答吸烟问题。",
        }
    )
    result = await agent.evaluate([], force=True)
    assert result.is_deviation is True
    assert result.constraint_prompt.startswith("简短回答后")


@pytest.mark.asyncio
async def test_empty_task_list_is_complete():
    """空任务列表的进度应为100%。"""
    agent, _ = make_agent(questions=[])
    result = await agent.evaluate([], force=True)
    assert result.progress_percentage == 100.0
    assert result.remaining_questions == []


def test_state_dump_and_restore():
    """运行态应可跨 Celery 重启恢复。"""
    agent, _ = make_agent()
    agent.restore_state(
        {"turn_counter": 9, "completed_questions": ["smoking", "unknown"]}
    )
    assert agent.dump_state() == {
        "turn_counter": 9,
        "completed_questions": ["smoking"],
    }


@pytest.mark.asyncio
async def test_model_request_contains_configured_limits():
    """模型请求应使用配置的模型、低温度和输出上限。"""
    agent, llm = make_agent()
    await agent.evaluate([], force=True)
    request = llm.chat.completions.create.await_args.kwargs
    assert request["model"] == "qwen-plus"
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == 512
    assert request["response_format"] == {"type": "json_object"}
