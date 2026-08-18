"""Dialog Agent 真实模型问句生成单元测试。"""

from types import SimpleNamespace

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.workers.dialog_agent_runner import DialogAgentRunner


class StubModel:
    """仅用于验证 Runner 是否调用真实模型接口的测试替身。"""

    model_name = "qwen3.5-flash"

    def __init__(self, content: str):
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=self.content)


def make_runner(model):
    return DialogAgentRunner(
        session_id="SESS-TEST",
        patient_info={"name": "测试患者"},
        scale_codes=["demo"],
        model=model,
        redis_client=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_opening_question_comes_from_model():
    """首问必须来自模型，不能直接返回量表原文。"""
    model = StubModel("您好，请问您最近的饮食情况怎么样？")
    runner = make_runner(model)
    question = QuestionTask(
        question_id=1,
        question_code="diet",
        question_name="饮食情况",
        patient_text="请问您平时饮食情况如何？",
        question_type="文本",
        required=True,
        sort_no=1,
    )

    result = await runner._generate_opening_question(question)

    assert result == "您好，请问您最近的饮食情况怎么样？"
    assert model.messages


@pytest.mark.asyncio
async def test_empty_model_opening_is_rejected():
    """模型没有返回问句时必须失败，不能静默回退。"""
    runner = make_runner(StubModel(""))
    question = QuestionTask(
        question_id=1,
        question_code="diet",
        question_name="饮食情况",
        patient_text="请问您平时饮食情况如何？",
        question_type="文本",
        required=True,
        sort_no=1,
    )

    with pytest.raises(RuntimeError, match="未返回首问"):
        await runner._generate_opening_question(question)
