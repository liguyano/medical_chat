"""Schedule Agent 提示词单元测试。"""

from medagent.agents.service_agent.schedule_agent import QuestionOption, QuestionTask
from medagent.agents.service_agent.schedule_agent.prompts import (
    DEVIATION_CHECK_SYSTEM_PROMPT,
    _format_dialog_history,
    _format_remaining_tasks,
    build_deviation_check_prompt,
    get_few_shot_examples_text,
)


def make_task(index: int, *, required: bool = True) -> QuestionTask:
    """创建提示词测试任务。"""
    return QuestionTask(
        question_id=index,
        question_code=f"q{index}",
        question_name=f"问题{index}",
        patient_text=f"请回答问题{index}",
        question_type="单选",
        required=required,
        sort_no=index,
        options=[
            QuestionOption(
                option_code="yes",
                option_label="是",
                option_value="yes",
            )
        ],
    )


def test_system_prompt_requires_completed_question_evidence():
    """系统提示必须约束模型仅按证据标记完成题目。"""
    assert "completed_questions" in DEVIATION_CHECK_SYSTEM_PROMPT
    assert "不允许猜测" in DEVIATION_CHECK_SYSTEM_PROMPT
    assert "teach-back" in DEVIATION_CHECK_SYSTEM_PROMPT
    assert "用自己的话复述" in DEVIATION_CHECK_SYSTEM_PROMPT


def test_remaining_tasks_include_required_optional_and_options():
    """任务文本应包含必答标记、选答标记和选项。"""
    text = _format_remaining_tasks(
        [make_task(1), make_task(2, required=False)]
    )
    assert "【必答】" in text
    assert "【可选】" in text
    assert "可选项：是" in text


def test_remaining_tasks_are_limited_to_five():
    """长任务列表只展示前5题并给出剩余数量。"""
    text = _format_remaining_tasks([make_task(index) for index in range(1, 8)])
    assert "还有 2 个问题待完成" in text
    assert "请回答问题6" not in text


def test_empty_task_and_history_have_explicit_placeholders():
    """空输入应使用明确占位文本。"""
    assert _format_remaining_tasks([]) == "（所有问题已完成）"
    assert _format_dialog_history([]) == "（暂无对话）"


def test_dialog_roles_are_localized():
    """对话角色应转换为模型易读的中文标签。"""
    text = _format_dialog_history(
        [
            {"role": "assistant", "content": "您好"},
            {"role": "user", "content": "你好"},
            {"role": "system", "content": "约束"},
        ]
    )
    assert text.splitlines() == ["AI: 您好", "患者: 你好", "系统: 约束"]


def test_user_prompt_contains_context_and_few_shots():
    """最终提示应同时包含任务、历史、轮次和示例。"""
    prompt = build_deviation_check_prompt(
        [make_task(1)],
        [{"role": "user", "content": "回答"}],
        5,
    )
    assert "第 5 轮" in prompt
    assert "q1" in prompt
    assert "患者: 回答" in prompt
    assert "正常追问场景" in prompt


def test_few_shot_examples_cover_four_scenarios():
    """Few-shot 应覆盖既定四类场景。"""
    text = get_few_shot_examples_text()
    assert text.count("### 示例") == 4
    for scenario in ("正常追问场景", "偏离场景", "共情场景", "宣教场景"):
        assert scenario in text
