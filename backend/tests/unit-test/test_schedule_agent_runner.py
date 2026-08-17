"""Schedule Agent 应用层运行器单元测试。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.configs.app_config import ModelConfig
from app.schemas.events import ConstraintEvent, SessionEndEvent
from app.workers.schedule_agent_runner import (
    ScheduleAgentRunner,
    decode_stream_fields,
)


class FakeLoader:
    """可控量表加载器。"""

    def __init__(self, questions):
        self.questions = questions

    async def load_questions_by_scale_codes(self, scale_codes):
        return self.questions


class FakeHistory:
    """可控对话历史管理器。"""

    def __init__(self, messages=None):
        self.messages = messages or []

    async def get_dialog_history(self, session_id, limit=None):
        return self.messages

    @staticmethod
    def format_for_langchain(history):
        return history


class FakeRedis:
    """内存 Redis 包装器替身。"""

    def __init__(self, reads=None, state=None, set_success=True):
        self.reads = list(reads or [])
        self.state = state
        self.set_success = set_success
        self.set_calls = []
        self.xread_calls = []

    def get(self, key):
        return self.state

    def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))
        return self.set_success

    def xread(self, streams, count=None, block=None):
        self.xread_calls.append((streams, count, block))
        return self.reads.pop(0) if self.reads else []


class FakePublisher:
    """收集已发布事件。"""

    def __init__(self, events):
        self.events = events

    def publish(self, event):
        self.events.append(event)
        return "1-0"


def question() -> QuestionTask:
    """创建单问题任务。"""
    return QuestionTask(
        question_id=1,
        question_code="smoking",
        question_name="吸烟",
        patient_text="您是否吸烟？",
        question_type="单选",
        required=True,
        sort_no=1,
    )


def llm(payload):
    """创建模型替身。"""
    create = AsyncMock()
    create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(payload, ensure_ascii=False)
                )
            )
        ]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def model_config() -> ModelConfig:
    """创建运行器模型配置。"""
    return ModelConfig(
        name="qwen-plus",
        display_name="Qwen Plus",
        model="qwen-plus",
        api_base="https://example.com/v1",
        api_key="key",
    )


def dialog_event(
    message_id=b"1-0",
    *,
    tool_calls=None,
    event_type=b"dialog_turn",
):
    """创建 Redis Stream 事件。"""
    fields = {
        b"event_type": event_type,
        b"turn_number": b"1",
        b"tool_calls": json.dumps(tool_calls).encode("utf-8"),
    }
    return [(b"dialog_stream:session", [(message_id, fields)])]


def make_runner(redis, payload, *, questions=None, history=None, events=None):
    """创建运行器及事件收集器。"""
    published = events if events is not None else []
    return (
        ScheduleAgentRunner(
            loader=FakeLoader([question()] if questions is None else questions),
            history_manager=FakeHistory(history),
            redis_client=redis,
            publisher_factory=lambda _: FakePublisher(published),
            llm_client=llm(payload),
            model_config=model_config(),
            block_ms=0,
            max_idle_reads=1,
        ),
        published,
    )


def test_decode_stream_fields_handles_bytes_json_and_plain_values():
    """Redis bytes 与 JSON 字段应正确解码。"""
    decoded = decode_stream_fields(
        {
            b"event_type": b"dialog_turn",
            b"tool_calls": b'[{"name":"tool"}]',
            "turn_number": "5",
        }
    )
    assert decoded == {
        "event_type": "dialog_turn",
        "tool_calls": [{"name": "tool"}],
        "turn_number": "5",
    }


def test_decode_stream_fields_keeps_invalid_json(caplog):
    """损坏 JSON 应记录警告且保留原值。"""
    decoded = decode_stream_fields({b"tool_calls": b"invalid"})
    assert decoded["tool_calls"] == "invalid"
    assert "JSON 字段解析失败" in caplog.text


@pytest.mark.asyncio
async def test_missing_scale_codes_fails_without_reading_stream():
    """缺少量表编码应快速失败。"""
    redis = FakeRedis()
    runner, _ = make_runner(redis, {})
    result = await runner.run("session", scale_codes=[])
    assert result == {"status": "failed", "reason": "missing_scale_codes"}
    assert redis.xread_calls == []


@pytest.mark.asyncio
async def test_no_loaded_questions_fails():
    """量表无可用问题时不得启动事件循环。"""
    runner, _ = make_runner(FakeRedis(), {}, questions=[])
    result = await runner.run("session", scale_codes=["unknown"])
    assert result == {"status": "failed", "reason": "no_questions_loaded"}


@pytest.mark.asyncio
async def test_idle_timeout_is_controllable_without_sleep():
    """空闲超时使用可控读取次数，不依赖长时间 sleep。"""
    runner, _ = make_runner(FakeRedis(reads=[[]]), {})
    result = await runner.run("session", scale_codes=["scale"])
    assert result["status"] == "idle_timeout"
    assert result["turns"] == 0


@pytest.mark.asyncio
async def test_non_dialog_event_is_ignored_but_checkpointed():
    """非对话轮次事件不调用模型，但必须推进消费位置。"""
    redis = FakeRedis(reads=[dialog_event(event_type=b"dialog_text"), []])
    runner, _ = make_runner(redis, {})
    result = await runner.run("session", scale_codes=["scale"])
    assert result["status"] == "idle_timeout"
    assert redis.set_calls[-1][1]["last_event_id"] == "1-0"


@pytest.mark.asyncio
async def test_deviation_publishes_constraint_event():
    """偏离结果应发布约束事件。"""
    redis = FakeRedis(reads=[dialog_event(), []])
    runner, events = make_runner(
        redis,
        {
            "is_deviation": True,
            "completed_questions": [],
            "suggested_action": "请回到量表。",
        },
    )
    result = await runner.run(
        "session",
        scale_codes=["scale"],
        check_interval=1,
    )
    assert result["status"] == "idle_timeout"
    assert isinstance(events[0], ConstraintEvent)
    assert events[0].constraint_prompt == "请回到量表。"


@pytest.mark.asyncio
async def test_completed_assessment_publishes_end_and_exits():
    """所有问题完成后应立即发布会话结束并退出。"""
    redis = FakeRedis(reads=[dialog_event()])
    runner, events = make_runner(
        redis,
        {
            "is_deviation": False,
            "completed_questions": ["smoking"],
        },
    )
    result = await runner.run(
        "session",
        scale_codes=["scale"],
        check_interval=1,
    )
    assert result["status"] == "completed"
    assert isinstance(events[-1], SessionEndEvent)
    assert events[-1].total_turns == 1


@pytest.mark.asyncio
async def test_tool_call_alias_shape_is_accepted():
    """DialogTurnEvent 的 tool_name/tool_args 结构应被识别。"""
    redis = FakeRedis(
        reads=[
            dialog_event(
                tool_calls=[
                    {
                        "tool_name": "get_education_material",
                        "tool_args": {"category": "tobacco"},
                    }
                ]
            ),
            [],
        ]
    )
    runner, events = make_runner(
        redis,
        {"is_deviation": False, "completed_questions": []},
        history=[{"role": "user", "content": "我吸烟"}],
    )
    await runner.run("session", scale_codes=["scale"], check_interval=1)
    assert events == []


@pytest.mark.asyncio
async def test_state_restore_uses_last_event_id_and_turn_counter():
    """重启后应从检查点继续消费且恢复轮次。"""
    redis = FakeRedis(
        reads=[[]],
        state={
            "turn_counter": 9,
            "completed_questions": [],
            "last_event_id": "8-0",
        },
    )
    runner, _ = make_runner(redis, {})
    result = await runner.run("session", scale_codes=["scale"])
    assert result["turns"] == 9
    assert redis.xread_calls[0][0] == {"dialog_stream:session": "8-0"}


@pytest.mark.asyncio
async def test_state_save_failure_is_not_silenced():
    """检查点保存失败必须让 Celery 上层触发重试。"""
    redis = FakeRedis(
        reads=[dialog_event(event_type=b"dialog_text")],
        set_success=False,
    )
    runner, _ = make_runner(redis, {})
    with pytest.raises(RuntimeError, match="状态保存失败"):
        await runner.run("session", scale_codes=["scale"])
