"""Dialog Agent 真实模型问句生成单元测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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


@pytest.mark.asyncio
async def test_completion_message_uses_cicare_exit_guidance():
    """进度完整后的结束语应说明复核、下一步安排和求助方式。"""
    model = StubModel("感谢您的配合，护士会复核记录并安排后续护理。若仍有不适，请及时呼叫医护人员。")
    runner = make_runner(model)

    result = await runner._generate_completion_message()

    assert "护士会复核" in result
    system_prompt = model.messages[0].content
    assert "CICARE Exit" in system_prompt
    assert "全部必填护理评估信息完整" in system_prompt


class DummyDb:
    """提供完成流程所需的最小数据库会话替身。"""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, _statement):
        return 4


@pytest.mark.asyncio
async def test_completion_persists_exit_before_completing_assessment(monkeypatch):
    """结束语必须先落库，之后才能把会话和任务提交为完成。"""
    from app.workers import dialog_agent_runner as runner_module

    order: list[str] = []
    progress = SimpleNamespace(completed=True, current=3, total=3)
    monkeypatch.setattr(runner_module.model_base, "SessionLocal", lambda: DummyDb())
    monkeypatch.setattr(
        runner_module,
        "refresh_assessment_progress",
        Mock(side_effect=lambda *_args: order.append("refresh") or progress),
    )
    monkeypatch.setattr(
        runner_module,
        "complete_assessment_session",
        Mock(side_effect=lambda *_args: order.append("complete") or progress),
    )

    runner = make_runner(StubModel("结束语"))
    runner.task_id = 8
    runner.interaction_session_id = 9
    runner._find_message_by_no = Mock(return_value=None)
    runner._start_generation = Mock(return_value="1-0")
    runner._generate_completion_message = AsyncMock(
        side_effect=lambda **_kwargs: order.append("generate") or "感谢您的配合。"
    )
    runner.history = SimpleNamespace(
        save_message=AsyncMock(
            side_effect=lambda *_args, **_kwargs: (
                order.append("save_exit")
                or SimpleNamespace(
                    message_no="MSG-END",
                    turn_no=5,
                    content_text="感谢您的配合。",
                )
            )
        )
    )

    def publish(event):
        order.append(type(event).__name__)
        return "2-0"

    runner.publisher = SimpleNamespace(publish=publish)
    runner.output_store = SimpleNamespace(
        complete=Mock(side_effect=lambda **_kwargs: order.append("snapshot")),
        fail=Mock(),
    )

    result = await runner._run_completion()

    assert result["status"] == "completed"
    assert order.index("generate") < order.index("save_exit")
    assert order.index("save_exit") < order.index("complete")
    assert order.index("complete") < order.index("SessionEndEvent")


@pytest.mark.asyncio
async def test_completion_generation_failure_does_not_complete_assessment(
    monkeypatch,
):
    """结束语生成失败时不得提前提交评估完成状态。"""
    from app.workers import dialog_agent_runner as runner_module

    progress = SimpleNamespace(completed=True, current=3, total=3)
    complete = Mock(return_value=progress)
    monkeypatch.setattr(runner_module.model_base, "SessionLocal", lambda: DummyDb())
    monkeypatch.setattr(
        runner_module,
        "refresh_assessment_progress",
        Mock(return_value=progress),
    )
    monkeypatch.setattr(runner_module, "complete_assessment_session", complete)

    runner = make_runner(StubModel(""))
    runner.task_id = 8
    runner.interaction_session_id = 9
    runner._find_message_by_no = Mock(return_value=None)
    runner._start_generation = Mock(return_value="1-0")
    runner._generate_completion_message = AsyncMock(
        side_effect=RuntimeError("模型失败")
    )
    runner.output_store = SimpleNamespace(fail=Mock())
    runner.publisher = SimpleNamespace(publish=Mock(return_value="2-0"))

    with pytest.raises(RuntimeError, match="模型失败"):
        await runner._run_completion()

    complete.assert_not_called()
    runner.output_store.fail.assert_called_once()
