"""Schedule Agent 单轮运行器测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.workers.schedule_agent_runner import ScheduleAgentRunner


def question() -> QuestionTask:
    """创建测试题目。"""
    return QuestionTask(
        question_id=1,
        question_code="q1",
        question_name="问题",
        patient_text="请回答问题",
        question_type="文本",
        required=True,
        sort_no=1,
    )


class FakeLoader:
    """测试量表加载器。"""

    def __init__(self, questions):
        self.questions = questions

    async def load_questions_by_scale_codes(self, _scale_codes):
        return self.questions


class FakeHistory:
    """测试历史管理器。"""

    async def get_dialog_history(self, _session_id, *, limit=None, offset=0):
        return []

    @staticmethod
    def format_for_langchain(_history):
        return []


class FakeRedis:
    """测试 Redis。"""

    def __init__(self, state=None):
        self.state = state
        self.saved = None
        self.values = {}

    def get(self, key):
        if key in self.values:
            return self.values[key]
        return self.state if key.startswith("schedule_agent:state:") else None

    def set(self, key, value, ex=None):
        self.saved = value
        self.values[key] = value
        return True


class FakePublisher:
    """测试事件发布器。"""

    def __init__(self, events):
        self.events = events

    def publish(self, event):
        self.events.append(event)
        return "1-0"


@pytest.mark.asyncio
async def test_missing_scale_codes_fails_without_agent_creation():
    """缺少量表编码应快速失败。"""
    runner = ScheduleAgentRunner(
        loader=FakeLoader([question()]),
        history_manager=FakeHistory(),
        redis_client=FakeRedis(),
        publisher_factory=lambda _session: FakePublisher([]),
        model=object(),
    )

    result = await runner.run("session", scale_codes=[], source_message_id="msg")

    assert result == {"status": "failed", "reason": "missing_scale_codes"}


@pytest.mark.asyncio
async def test_opening_prepares_recoverable_task_todo():
    """首问前必须由 Schedule Agent 生成并保存 Task-todo。"""
    redis = FakeRedis()
    runner = ScheduleAgentRunner(
        loader=FakeLoader([question()]),
        history_manager=FakeHistory(),
        redis_client=redis,
        publisher_factory=lambda _session: FakePublisher([]),
        model=object(),
    )

    result = await runner.run("session", scale_codes=["adl"])

    assert result["status"] == "prepared"
    assert result["question_count"] == 1
    assert redis.values["schedule_agent:task_todo:session"]["tasks"][0][
        "question_code"
    ] == "q1"


@pytest.mark.asyncio
async def test_single_turn_evaluates_real_schedule_agent(monkeypatch):
    """患者答案任务只执行一轮并保存处理游标。"""
    import app.workers.schedule_agent_runner as module

    events = []
    redis = FakeRedis()
    agent = SimpleNamespace(
        restore_state=Mock(),
        dump_state=Mock(
            return_value={"turn_counter": 1, "completed_questions": []}
        ),
        evaluate=AsyncMock(
            return_value=SimpleNamespace(
                is_deviation=True,
                missing_tool_calls=[],
                constraint_prompt="请继续量表问诊",
                remaining_questions=["q1"],
            )
        ),
    )
    monkeypatch.setattr(module, "create_schedule_agent", Mock(return_value=agent))
    runner = ScheduleAgentRunner(
        loader=FakeLoader([question()]),
        history_manager=FakeHistory(),
        redis_client=redis,
        publisher_factory=lambda _session: FakePublisher(events),
        model=object(),
    )
    monkeypatch.setattr(runner, "_load_task_id", lambda _session: 10)
    monkeypatch.setattr(runner, "_load_recent_tool_calls", lambda _session: [])

    result = await runner.run(
        "session",
        scale_codes=["adl"],
        source_message_id="patient-msg-1",
        source_event_id="2-0",
    )

    assert result["status"] == "turn_completed"
    assert agent.evaluate.await_count == 1
    assert len(events) == 1
    assert redis.values["schedule_agent:state:session"]["processed_message_ids"] == [
        "patient-msg-1"
    ]
    assert (
        redis.values["schedule_agent:guidance:session"]["constraint_prompt"]
        == "请继续量表问诊"
    )


@pytest.mark.asyncio
async def test_processed_message_is_idempotent():
    """同一患者答案重复派发时不得再次调用模型。"""
    redis = FakeRedis({"processed_message_ids": ["patient-msg-1"]})
    runner = ScheduleAgentRunner(
        loader=FakeLoader([question()]),
        history_manager=FakeHistory(),
        redis_client=redis,
        publisher_factory=lambda _session: FakePublisher([]),
        model=object(),
    )

    result = await runner.run(
        "session",
        scale_codes=["adl"],
        source_message_id="patient-msg-1",
    )

    assert result["status"] == "already_completed"
