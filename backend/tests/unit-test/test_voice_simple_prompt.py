from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.services.voice_gateway import VOICE_TOOLS, VoiceGateway


def test_voice_receives_only_questions_without_route_or_provisional_control():
    tasks = [
        QuestionTask(
            question_id=i,
            question_code=f"q{i}",
            question_name="测试",
            patient_text=f"过去24小时的原始问题{i}",
            question_type="文本",
            required=True,
            sort_no=i,
        )
        for i in (1, 2)
    ]
    prompt = VoiceGateway._build_remaining_assessment_instructions({}, tasks)
    for task in tasks:
        assert prompt.count(task.patient_text) == 1
    for retired in (
        "CICARE",
        "生活话题引导",
        "自然经历式接话",
        "mark_patient_response_heard",
        "话题路线",
        "暂放待核实",
    ):
        assert retired not in prompt
    assert [t["function"]["name"] for t in VOICE_TOOLS] == ["request_assessment_finish"]
    assert "后台会边聊边提取答案" in prompt


async def _finish_guard_case():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    session = SimpleNamespace(
        closed=False,
        speech_active=False,
        responding=False,
        response_requested=True,
        session_no="synthetic",
        client=SimpleNamespace(create_response=AsyncMock()),
    )
    gateway = VoiceGateway()
    gateway._handle_assessment_finish_tool = AsyncMock(
        return_value={"completed": False, "remaining_questions": ["q"]}
    )
    await gateway._review_spoken_finish(session, response_id="old-response")
    session.client.create_response.assert_not_awaited()


def test_spoken_finish_does_not_duplicate_an_already_requested_response():
    import asyncio

    asyncio.run(_finish_guard_case())
