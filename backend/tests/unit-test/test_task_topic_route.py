"""任务创建时的话题路线、覆盖边界与消费回归。"""

from types import SimpleNamespace

import pytest
from medagent.agents.service_agent.schedule_agent.models import (
    QuestionTask,
    ScheduleTaskTodo,
    TopicRouteStep,
)
from medagent.agents.service_agent.schedule_agent.topic_route import render_topic_route


def question(code):
    return QuestionTask(
        question_id=int(code[-1]),
        question_code=code,
        question_name=code,
        patient_text=f"{code}的原题",
        question_type="文本",
        required=True,
        sort_no=1,
    )


def step(codes, topic_id="daily"):
    return TopicRouteStep(
        topic_id=topic_id,
        title="日常饮食",
        question_codes=codes,
        entry_question="您最近一顿吃了什么？",
        follow_up_guidance=["从食物聊到餐具与动作"],
        answer_branches=["不想聊饮食则先聊其他生活场景"],
        evidence_rules=["餐具偏好不是进食能力证据"],
        transition_to_next="从饭后活动连接出门散步",
    )


def plan(steps):
    return ScheduleTaskTodo(
        session_id="s",
        tasks=[question("q1"), question("q2")],
        topic_route=steps,
        plan_version="2.0",
    )


@pytest.mark.parametrize("codes", [[], ["q1"], ["q1", "q2", "unknown"], ["q1", "q2", "q1"]])
def test_route_rejects_missing_unknown_and_duplicate_targets(codes):
    with pytest.raises(ValueError):
        plan([] if not codes else [step(codes)])


def test_route_roundtrip_and_completed_topics_are_filtered():
    original = plan([step(["q1"], "food"), step(["q2"], "walk")])
    restored = ScheduleTaskTodo.model_validate(original.model_dump(mode="json"))
    rendered = render_topic_route(restored.topic_route, [question("q2")])
    assert "walk" in rendered and "food" not in rendered
    assert "q1" not in rendered
    assert "路线走完不等于评估完成" in rendered


def test_duplicate_topic_ids_are_rejected():
    with pytest.raises(ValueError):
        plan([step(["q1"]), step(["q2"])])


def test_redis_miss_recovers_persisted_route(monkeypatch):
    from app.services import task_preparation_service as service
    from app.workers.schedule_task_store import ScheduleTaskStore

    expected = plan([step(["q1", "q2"])])
    monkeypatch.setattr(
        service, "load_prepared_plan_payload", lambda _: expected.model_dump(mode="json")
    )
    values = {}
    redis = SimpleNamespace(
        get=lambda key: values.get(key),
        set=lambda key, value, ex: values.setdefault(key, value) is not None,
    )
    restored = ScheduleTaskStore(redis).get_plan("s")
    assert restored.topic_route == expected.topic_route
    assert values["schedule_agent:task_todo:s"]["topic_route"]


def test_preparation_snapshot_restores_all_route_fields(monkeypatch):
    from app.services import task_preparation_service as service

    expected = plan([step(["q1", "q2"])])
    task = SimpleNamespace(
        preparation_detail={
            "stages": {
                "schedule_prepare": {
                    "status": "completed",
                    "output": {
                        "questions": [q.model_dump() for q in expected.tasks],
                        "topic_route": [s.model_dump() for s in expected.topic_route],
                        "plan_version": "2.0",
                    },
                }
            }
        }
    )
    monkeypatch.setattr(service, "_with_session", lambda fn: fn(object()))
    monkeypatch.setattr(service, "_load_task", lambda *_: task)
    recovered = ScheduleTaskTodo.model_validate(service.load_prepared_plan_payload("s"))
    assert recovered.topic_route == expected.topic_route


def test_real_voice_instruction_uses_task_route():
    from app.services.voice_gateway import VoiceGateway

    route = [step(["q1", "q2"])]
    prompt = VoiceGateway._build_remaining_assessment_instructions(
        {}, [question("q2")], topic_route=route
    )
    assert "创建任务时生成的话题路线" not in prompt
    assert "您最近一顿吃了什么" not in prompt
    assert "从食物聊到餐具与动作" not in prompt
    assert "remaining_guidance" not in prompt
    assert prompt.count(question("q2").patient_text) == 1
    assert '"question_id": 2' in prompt
