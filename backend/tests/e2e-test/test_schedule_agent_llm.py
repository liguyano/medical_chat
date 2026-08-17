"""Schedule Agent 真实模型偏离检测端到端测试。"""

import os

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask, ScheduleAgent
from medagent.configs.model_config import ModelConfig, ModelType
from medagent.providers import create_chat_model

SCENARIOS = [
    (
        False,
        [
            {"role": "assistant", "content": "请问您平时是否吸烟？"},
            {"role": "user", "content": "不吸烟。"},
        ],
    ),
    (
        False,
        [
            {"role": "assistant", "content": "请问您平时是否吸烟？"},
            {"role": "user", "content": "每天半包。"},
            {"role": "assistant", "content": "大概持续多少年了？"},
            {"role": "user", "content": "二十年左右。"},
        ],
    ),
    (
        False,
        [
            {"role": "assistant", "content": "您最近有疼痛吗？"},
            {"role": "user", "content": "很疼，我有点害怕。"},
            {
                "role": "assistant",
                "content": "我理解您现在很难受，我们会帮助您。请用0到10分描述疼痛程度。",
            },
        ],
    ),
    (
        False,
        [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "每天一包。"},
            {
                "role": "assistant",
                "content": "吸烟会影响恢复，我先为您做简短戒烟宣教，然后继续评估。",
            },
        ],
    ),
    (
        False,
        [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "食堂在哪里？"},
            {
                "role": "assistant",
                "content": "稍后护士会告诉您。我们先继续评估，请问您是否吸烟？",
            },
            {"role": "user", "content": "不吸烟。"},
        ],
    ),
    (
        True,
        [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "食堂在哪里？"},
            {"role": "assistant", "content": "食堂在一楼。"},
            {"role": "user", "content": "几点开门？"},
            {"role": "assistant", "content": "早上七点，还有别的问题吗？"},
        ],
    ),
    (
        True,
        [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "我不吸烟。"},
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "刚才说了不吸烟。"},
            {"role": "assistant", "content": "请再回答一次您是否吸烟？"},
        ],
    ),
]


@pytest.mark.asyncio
@pytest.mark.real_llm
async def test_real_llm_deviation_accuracy_exceeds_85_percent():
    """七类真实语义场景准确率必须超过85%。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        pytest.skip("未配置 DASHSCOPE_API_KEY，无法执行真实模型测试")

    model = create_chat_model(
        ModelConfig(
            name="qwen-plus-precise",
            display_name="Qwen Plus 确定性",
            type=ModelType.LANGUAGE,
            model="qwen-plus",
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            timeout=60.0,
            max_retries=1,
            temperature=0.1,
            max_tokens=500,
        )
    )
    matches: list[bool] = []
    details: list[str] = []
    for index, (expected, history) in enumerate(SCENARIOS, 1):
        agent = ScheduleAgent(
            session_id=f"real-llm-{index}",
            task_list=[
                QuestionTask(
                    question_id=1,
                    question_code="smoking",
                    question_name="吸烟情况",
                    patient_text="请问您是否吸烟？",
                    question_type="单选",
                    required=True,
                    sort_no=1,
                )
            ],
            model=model,
            check_interval=1,
        )
        tool_calls = (
            [
                {
                    "name": "get_education_material",
                    "arguments": {"category": "tobacco"},
                }
            ]
            if index in {2, 4}
            else []
        )
        result = await agent.evaluate(history, tool_calls=tool_calls)
        matched = result.is_deviation is expected
        matches.append(matched)
        if not matched:
            details.append(
                f"场景{index}: expected={expected}, actual={result.is_deviation}"
            )

    accuracy = sum(matches) / len(matches)
    assert accuracy > 0.85, f"准确率={accuracy:.2%}; " + "; ".join(details)
