"""Dialog Agent 应用层 Redis 与依赖适配器测试。"""

from unittest.mock import Mock

import pytest
from medagent.agents.service_agent.dialog_agent.tools import execute_tool

from app.utils import redis_client as redis_module
from app.workers import dialog_agent_runtime as runtime_module


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
    source = runtime_module.RedisConstraintSource(redis)

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
        runtime_module.RedisConstraintSource(redis)("session")


def test_runtime_dependencies_inject_real_tool_executor(monkeypatch):
    """运行时依赖应注入真实工具执行器和三个应用适配器。"""
    redis = FakeRedis([])
    state_store = object()
    history_store = object()
    timeout_manager = Mock()

    monkeypatch.setattr(redis_module, "get_redis", lambda: redis)
    monkeypatch.setattr(runtime_module, "AsyncAgentStateManager", lambda: state_store)
    monkeypatch.setattr(runtime_module, "DialogHistoryManager", lambda: history_store)
    monkeypatch.setattr(runtime_module, "SessionTimeoutManager", lambda: timeout_manager)

    dependencies = runtime_module.get_runtime_dependencies("session")

    assert dependencies["state_store"] is state_store
    assert dependencies["history_store"] is history_store
    assert dependencies["tool_executor"] is execute_tool
    assert len(dependencies["middlewares"]) == 4
