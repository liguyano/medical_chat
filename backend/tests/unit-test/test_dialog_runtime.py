"""Dialog Agent 应用层 Redis 与事件适配器测试。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from medagent.agents.service_agent.dialog_agent import DialogEngine
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.schemas.events import EventType
from app.workers.dialog_agent_runtime import (
    AppDialogEventSink,
    RedisConstraintSource,
    build_dialog_agent,
)


class FakeRedis:
    """支持约束游标测试的 Redis 替身。"""

    def __init__(self, reads, *, set_result=True):
        self.reads = list(reads)
        self.values = {}
        self.set_result = set_result
        self.xread_calls = []
        self.set_calls = []

    def get(self, key):
        return self.values.get(key)

    def xread(self, streams, count=None, block=None):
        self.xread_calls.append((streams, count, block))
        return self.reads.pop(0) if self.reads else []

    def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))
        if self.set_result:
            self.values[key] = value
        return self.set_result


def stream_entries():
    return [
        (
            b"dialog_stream:session",
            [
                (
                    b"1-0",
                    {
                        b"event_type": b"dialog_turn",
                        b"answer": "正常回答".encode(),
                    },
                ),
                (
                    b"2-0",
                    {
                        b"event_type": b"constraint",
                        b"constraint_prompt": "请回到量表".encode(),
                    },
                ),
            ],
        )
    ]


def test_constraint_source_consumes_flat_stream_and_saves_cursor():
    """适配器应读取统一 dialog_stream 扁平字段并保存最后事件 ID。"""
    redis = FakeRedis([stream_entries(), []])
    source = RedisConstraintSource(redis)

    first = source("session")
    second = source("session")

    assert first == ["请回到量表"]
    assert second == []
    assert redis.xread_calls[0][0] == {"dialog_stream:session": "0"}
    assert redis.xread_calls[1][0] == {"dialog_stream:session": "2-0"}
    assert redis.set_calls == [
        ("dialog_agent:constraint_cursor:session", "2-0", 3600)
    ]


def test_constraint_source_raises_when_cursor_cannot_be_saved():
    """游标保存失败必须显式暴露，避免约束无限重复。"""
    redis = FakeRedis([stream_entries()], set_result=False)

    with pytest.raises(RuntimeError, match="约束游标保存失败"):
        RedisConstraintSource(redis)("session")


def test_app_event_sink_builds_pydantic_events(monkeypatch):
    """SDK 事件字典应转换为应用事件并交给统一发布器。"""
    import app.workers.dialog_agent_runtime as runtime_module

    published = []
    publisher = SimpleNamespace(
        publish=lambda event: published.append(event) or "1-0"
    )
    monkeypatch.setattr(
        runtime_module,
        "DialogEventPublisher",
        lambda _: publisher,
    )
    sink = AppDialogEventSink("session")

    turn_id = sink(
        {
            "event_type": "dialog_turn",
            "session_id": "session",
            "turn_number": 1,
            "question": "问题",
            "answer": "回答",
            "tool_calls": None,
        }
    )
    tool_id = sink(
        {
            "event_type": "tool_call",
            "session_id": "session",
            "turn_number": 1,
            "tool_name": "tool",
            "tool_args": {},
            "tool_result": {"success": True},
        }
    )

    assert turn_id == tool_id == "1-0"
    assert published[0].event_type == EventType.DIALOG_TURN
    assert published[1].event_type == EventType.TOOL_CALL


def test_app_event_sink_rejects_unknown_event(monkeypatch):
    """未知 SDK 事件类型不得静默发布。"""
    import app.workers.dialog_agent_runtime as runtime_module

    monkeypatch.setattr(
        runtime_module,
        "DialogEventPublisher",
        lambda _: SimpleNamespace(publish=Mock()),
    )
    sink = AppDialogEventSink("session")

    with pytest.raises(ValueError, match="不支持"):
        sink({"event_type": "unknown"})


class NoopEngine(DialogEngine):
    async def create_session(self, system_prompt, tools, **kwargs):
        return None

    async def send_input(self, input_data):
        return None

    async def stream_response(self):
        if False:
            yield {}

    async def send_tool_result(self, call_id, result):
        return None

    async def update_session(self, instructions=None, tools=None):
        return None

    async def close_session(self):
        return None


def test_builder_injects_all_application_adapters(monkeypatch):
    """App builder 应组装状态、历史、约束、事件和超时适配器。"""
    import app.workers.dialog_agent_runtime as runtime_module

    state_store = object()
    history_store = object()
    timeout = SimpleNamespace(update_activity=Mock(return_value=True))
    monkeypatch.setattr(
        runtime_module,
        "AsyncAgentStateManager",
        lambda: state_store,
    )
    monkeypatch.setattr(
        runtime_module,
        "DialogHistoryManager",
        lambda: history_store,
    )
    monkeypatch.setattr(
        runtime_module,
        "SessionTimeoutManager",
        lambda: timeout,
    )
    monkeypatch.setattr(
        runtime_module,
        "AppDialogEventSink",
        lambda _: Mock(),
    )
    question = QuestionTask(
        question_id=1,
        question_code="q1",
        question_name="问题",
        patient_text="请回答",
        question_type="文本",
        required=True,
        sort_no=1,
    )

    dialog = build_dialog_agent(
        session_id="session",
        patient_info={},
        task_list=[question],
        engine=NoopEngine(),
        redis_client=FakeRedis([]),
    )

    assert dialog.state_store is state_store
    assert dialog.history_store is history_store
    assert len(dialog.middleware.middlewares) == 4
