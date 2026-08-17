"""Schedule Agent 与真实 Redis Stream 集成测试。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.configs.app_config import ModelConfig
from app.schemas.events import ConstraintEvent, DialogTurnEvent, EventType
from app.utils.redis_client import RedisClient, init_redis
from app.workers.event_publisher import DialogEventPublisher
from app.workers.schedule_agent_runner import ScheduleAgentRunner, decode_stream_fields


class OneQuestionLoader:
    """返回一个固定问题。"""

    async def load_questions_by_scale_codes(self, scale_codes):
        return [
            QuestionTask(
                question_id=1,
                question_code="smoking",
                question_name="吸烟",
                patient_text="您是否吸烟？",
                question_type="单选",
                required=True,
                sort_no=1,
            )
        ]


class DictHistoryManager:
    """返回字典格式历史，避免本测试依赖 PostgreSQL。"""

    async def get_dialog_history(self, session_id, limit=None):
        return [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "我想问食堂在哪里"},
            {"role": "assistant", "content": "食堂在一楼"},
        ]

    @staticmethod
    def format_for_langchain(history):
        return history


def fake_llm():
    """返回稳定偏离判断。"""
    create = AsyncMock()
    create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "is_deviation": True,
                            "reason": "持续讨论食堂",
                            "completed_questions": [],
                            "suggested_action": "请回到吸烟评估。",
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


@pytest.fixture
def redis_client():
    """提供真实 Redis 并清理本测试创建的键。"""
    client = RedisClient(host="localhost", port=6379, db=0)
    if not client.ping():
        pytest.skip("Redis 测试环境不可用")
    init_redis(host="localhost", port=6379, db=0)
    keys: list[str] = []
    yield client, keys
    if keys:
        client.delete(*keys)
    client.close()


@pytest.mark.asyncio
async def test_runner_consumes_bytes_event_and_publishes_constraint(redis_client):
    """真实 Redis bytes 消息应被处理并发布约束事件。"""
    client, keys = redis_client
    session_id = f"schedule-test-{uuid4()}"
    stream_key = f"dialog_stream:{session_id}"
    state_key = f"schedule_agent:state:{session_id}"
    keys.extend([stream_key, state_key])

    DialogEventPublisher(session_id).publish(
        DialogTurnEvent(
            session_id=session_id,
            turn_number=1,
            question="食堂在哪里？",
            answer="食堂在一楼。",
        )
    )
    runner = ScheduleAgentRunner(
        loader=OneQuestionLoader(),
        history_manager=DictHistoryManager(),
        redis_client=client,
        publisher_factory=DialogEventPublisher,
        llm_client=fake_llm(),
        model_config=ModelConfig(
            name="qwen-plus",
            display_name="Qwen Plus",
            model="qwen-plus",
            api_base="https://example.com/v1",
            api_key="key",
        ),
        block_ms=1,
        max_idle_reads=1,
    )
    result = await runner.run(
        session_id,
        scale_codes=["test"],
        check_interval=1,
    )

    assert result["status"] == "idle_timeout"
    all_messages = client.xread({stream_key: "0"})
    events = [
        decode_stream_fields(fields)
        for _, message_list in all_messages
        for _, fields in message_list
    ]
    constraints = [
        event for event in events if event["event_type"] == EventType.CONSTRAINT.value
    ]
    assert len(constraints) == 1
    assert constraints[0]["constraint_prompt"] == "请回到吸烟评估。"
    state = client.get(state_key)
    assert state["turn_counter"] == 1
    assert state["last_event_id"]


def test_constraint_event_round_trip_preserves_remaining_tasks(redis_client):
    """复杂列表字段经 Redis Stream 往返后应保持结构。"""
    client, keys = redis_client
    session_id = f"schedule-test-{uuid4()}"
    stream_key = f"dialog_stream:{session_id}"
    keys.append(stream_key)

    DialogEventPublisher(session_id).publish(
        ConstraintEvent(
            session_id=session_id,
            constraint_type="deviation",
            constraint_prompt="回到量表",
            remaining_tasks=["q1", "q2"],
        )
    )
    messages = client.xread({stream_key: "0"})
    fields = messages[0][1][0][1]
    decoded = {key.decode(): value.decode() for key, value in fields.items()}
    assert json.loads(decoded["remaining_tasks"]) == ["q1", "q2"]
