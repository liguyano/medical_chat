"""Dialog Agent middleware 单元测试。"""

from unittest.mock import AsyncMock, Mock

import pytest
from medagent.agents.middlewares import (
    DialogMiddleware,
    EventPublishMiddleware,
    KeywordInterceptMiddleware,
    MiddlewareChain,
    ScheduleConstraintMiddleware,
    TimeoutMiddleware,
)


class RecordingMiddleware(DialogMiddleware):
    """记录调用顺序，可按阶段抛错。"""

    def __init__(self, name, calls, *, fail_before=False, fail_after=False):
        self.name = name
        self.calls = calls
        self.fail_before = fail_before
        self.fail_after = fail_after

    async def before_agent(self, context):
        self.calls.append(f"before:{self.name}")
        if self.fail_before:
            raise RuntimeError("before failed")

    async def after_agent(self, context, output):
        self.calls.append(f"after:{self.name}")
        if self.fail_after:
            raise RuntimeError("after failed")


@pytest.mark.asyncio
async def test_middleware_chain_preserves_order_and_isolates_failures():
    """一个中间件失败时后续钩子仍须执行。"""
    calls = []
    chain = MiddlewareChain(
        [
            RecordingMiddleware("one", calls, fail_before=True),
            RecordingMiddleware("two", calls, fail_after=True),
            RecordingMiddleware("three", calls),
        ]
    )

    await chain.execute_before({})
    await chain.execute_after({}, "output")

    assert calls == [
        "before:one",
        "before:two",
        "before:three",
        "after:one",
        "after:two",
        "after:three",
    ]


@pytest.mark.asyncio
async def test_keyword_middleware_matches_and_deduplicates_constraints():
    """同义关键词不得重复追加同一约束。"""
    middleware = KeywordInterceptMiddleware()
    context = {
        "patient_input": "我抽烟，也有吸烟史",
        "constraints": [],
    }

    await middleware.before_agent(context)
    await middleware.before_agent(context)

    assert len(context["constraints"]) == 1
    assert "get_education_material" in context["constraints"][0]
    assert "trigger_consent_form" in context["constraints"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patient_input",
    ["我不抽烟", "从不吸烟", "已经戒烟", "不喝酒", "无需手术"],
)
async def test_keyword_middleware_respects_negative_semantics(patient_input):
    """否定语义不得触发宣教或知情同意约束。"""
    context = {"patient_input": patient_input, "constraints": []}

    await KeywordInterceptMiddleware().before_agent(context)

    assert context["constraints"] == []


@pytest.mark.asyncio
async def test_schedule_constraint_accepts_sync_and_async_sources():
    """约束来源可为同步或异步适配器，并应去重。"""
    sync_context = {"session_id": "s1", "constraints": ["已有约束"]}
    await ScheduleConstraintMiddleware(
        lambda _: ["已有约束", "回到量表"]
    ).before_agent(sync_context)

    async_source = AsyncMock(return_value=["调用宣教工具"])
    async_context = {"session_id": "s2", "constraints": []}
    await ScheduleConstraintMiddleware(async_source).before_agent(async_context)

    assert sync_context["constraints"] == ["已有约束", "回到量表"]
    assert async_context["constraints"] == ["调用宣教工具"]
    async_source.assert_awaited_once_with("s2")


@pytest.mark.asyncio
async def test_schedule_constraint_failure_does_not_escape():
    """约束存储异常不得中断患者主对话。"""
    context = {"session_id": "s1", "constraints": []}

    await ScheduleConstraintMiddleware(
        Mock(side_effect=RuntimeError("redis failed"))
    ).before_agent(context)

    assert context["constraints"] == []


@pytest.mark.asyncio
async def test_event_publish_emits_turn_and_tool_events():
    """after hook 应发布一条轮次事件和逐条工具事件。"""
    events = []
    middleware = EventPublishMiddleware("session", events.append)
    context = {
        "turn_number": 3,
        "patient_input": "我吸烟",
        "tool_calls": [
            {
                "name": "get_education_material",
                "arguments": {"category": "tobacco"},
                "result": {"success": True},
            }
        ],
    }

    await middleware.after_agent(context, "我为您提供戒烟建议")

    assert [event["event_type"] for event in events] == [
        "dialog_turn",
        "tool_call",
    ]
    assert events[0]["question"] == "我吸烟"
    assert events[0]["tool_calls"] == context["tool_calls"]
    assert events[1]["tool_args"] == {"category": "tobacco"}


@pytest.mark.asyncio
async def test_event_publish_failure_does_not_escape():
    """事件发布失败不能击穿 Dialog Agent。"""
    middleware = EventPublishMiddleware(
        "session",
        Mock(side_effect=RuntimeError("publish failed")),
    )

    await middleware.after_agent({"turn_number": 1}, "answer")


@pytest.mark.asyncio
async def test_timeout_middleware_updates_before_and_after():
    """会话活动更新时间在对话前后都应刷新。"""
    updater = AsyncMock(return_value=True)
    middleware = TimeoutMiddleware(updater)
    context = {"session_id": "session"}

    await middleware.before_agent(context)
    await middleware.after_agent(context, "answer")

    assert updater.await_count == 2
    updater.assert_awaited_with("session")


@pytest.mark.asyncio
async def test_timeout_middleware_skips_missing_session_and_isolates_error():
    """缺少会话号应跳过，更新失败应被隔离。"""
    updater = Mock(side_effect=RuntimeError("redis failed"))
    middleware = TimeoutMiddleware(updater)

    await middleware.before_agent({})
    await middleware.after_agent({"session_id": "session"}, "answer")

    updater.assert_called_once_with("session")
