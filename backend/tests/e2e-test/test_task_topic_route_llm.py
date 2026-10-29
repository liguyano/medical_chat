"""使用合成题集验证任务准备阶段真实生成路线，不访问患者数据库。"""

import os
from pathlib import Path

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask, ScheduleAgent
from medagent.providers import create_structured_chat_model

from app.configs.app_config import get_app_config


@pytest.mark.asyncio
@pytest.mark.real_llm
async def test_task_preparation_generates_complete_topic_route():
    if os.getenv("RUN_TOPIC_LLM") != "1":
        pytest.skip("仅在显式授权真实模型后执行")
    tasks = [
        QuestionTask(
            question_id=i,
            question_code=code,
            question_name=name,
            patient_text=ref,
            question_type="文本",
            required=True,
            sort_no=i,
        )
        for i, code, name, ref in [
            (1, "vision", "视力", "看近处屏幕上的字是否清楚"),
            (2, "eating", "进食", "吃饭是否需要帮助"),
            (3, "sleep", "睡眠", "最近入睡和夜间醒来情况"),
        ]
    ]
    config = get_app_config().get_agent_model_config("schedule_agent")
    plan = await ScheduleAgent(
        "SYNTHETIC-ROUTE", tasks, create_structured_chat_model(config)
    ).prepare_task_todo({"age": 70})
    assert plan.plan_version == "2.0" and plan.topic_route
    assert {c for s in plan.topic_route for c in s.question_codes} == {"vision", "eating", "sleep"}
    for topic in plan.topic_route:
        print(
            f"\n路线：{topic.title} | {topic.question_codes} | 入口：{topic.entry_question} | 衔接：{topic.transition_to_next}",
            flush=True,
        )
        assert topic.entry_question.count("？") + topic.entry_question.count("?") <= 1
        if "eating" in topic.question_codes:
            assert not any(
                word in topic.entry_question
                for word in ["筷子", "勺子", "帮助", "帮忙", "自理", "自己吃"]
            )
    assert "您先休息" not in plan.topic_route[-1].transition_to_next
    if os.getenv("TOPIC_ROUTE_PLAN_OUT"):
        Path(os.environ["TOPIC_ROUTE_PLAN_OUT"]).write_text(
            plan.model_dump_json(indent=2), encoding="utf-8"
        )
