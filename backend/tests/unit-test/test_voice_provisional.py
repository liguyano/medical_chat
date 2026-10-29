import pytest

from app.services.voice_provisional import VoiceProvisionalState


def test_provisional_is_not_a_formal_answer_and_requires_real_quote():
    state = VoiceProvisionalState()
    state.begin_turn("m1", "可以自己夹")
    with pytest.raises(ValueError):
        state.mark([1], "别人喂饭", {1})
    with pytest.raises(ValueError):
        state.mark([99], "可以", {1})
    state.mark([1], "自己夹", {1})
    assert state.available({1, 2}) == {2}
    state.settle({1, 2}, {"m1"})
    assert state.available({1, 2}) == {2}
    state.begin_turn("m2", "喜欢散步")
    assert state.available({1, 2}) == {2}
    state.begin_turn("m3", "小区走走")
    assert state.available({1, 2}) == {1, 2}


def test_confirmed_fact_is_not_reopened_and_empty_quote_is_rejected():
    state = VoiceProvisionalState()
    state.begin_turn("m1", "好")
    with pytest.raises(ValueError):
        state.mark([1], "", {1})
    state.mark([1], "好", {1})
    state.settle({2}, {"m1"})
    assert not state.pending
    assert state.available({2}) == {2}


@pytest.mark.asyncio
async def test_gateway_initial_mark_changes_scope_without_clinical_write(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from medagent.agents.service_agent.schedule_agent import QuestionTask

    from app.services.voice_gateway import VoiceGateway
    from app.services.voice_turn_guard import VoiceTurnGuard

    tasks = [
        QuestionTask(
            question_id=i,
            question_code=f"q{i}",
            question_name="饮食",
            patient_text="过去一天吃饭情况",
            question_type="文本",
            required=True,
            sort_no=i,
        )
        for i in (1, 2)
    ]
    state = VoiceProvisionalState()
    state.begin_turn("m1", "可以自己夹")
    session = SimpleNamespace(
        task_list=tasks,
        provisional=state,
        scope_update_version=0,
        session_no="synthetic",
        closed=False,
        recovery_mode_active=False,
        recovery_instruction_active=False,
        patient_info={},
        topic_route=[],
        client=SimpleNamespace(update_instructions=AsyncMock()),
    )
    decision = SimpleNamespace(
        remaining_questions=tasks, progress=SimpleNamespace(remaining_question_ids=[1, 2])
    )
    monkeypatch.setattr(VoiceTurnGuard, "build_recovery_decision", lambda *_: decision)
    gateway = VoiceGateway()
    monkeypatch.setattr(gateway, "_schedule_progress_sync", lambda _: None)
    result = await gateway._mark_response_heard(session, {"question_ids": [1], "quote": "自己夹"})
    assert result["formal_answer"] is False
    session.client.update_instructions.assert_not_awaited()
    assert result["temporarily_held_question_ids"] == [1]
    assert result["continue_other_question_ids"] == [2]


@pytest.mark.asyncio
async def test_stale_scope_read_cannot_overwrite_newer_scope(monkeypatch):
    import asyncio
    import threading
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services.voice_gateway import VoiceGateway
    from app.services.voice_turn_guard import VoiceTurnGuard

    started = threading.Event()
    release = threading.Event()

    def slow_read(*_):
        started.set()
        release.wait(2)
        return SimpleNamespace(
            remaining_questions=[], progress=SimpleNamespace(remaining_question_ids=[])
        )

    monkeypatch.setattr(VoiceTurnGuard, "build_recovery_decision", slow_read)
    session = SimpleNamespace(
        scope_update_version=0,
        session_no="synthetic",
        task_list=[],
        closed=False,
        recovery_mode_active=False,
        recovery_instruction_active=False,
        client=SimpleNamespace(update_instructions=AsyncMock()),
    )
    task = asyncio.create_task(VoiceGateway()._refresh_conversation_scope(session))
    await asyncio.to_thread(started.wait, 1)
    session.scope_update_version += 1
    release.set()
    await task
    session.client.update_instructions.assert_not_awaited()


@pytest.mark.asyncio
async def test_extraction_arriving_after_timeout_still_refreshes_scope(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import app.services.voice_gateway as module

    state = VoiceProvisionalState()
    state.begin_turn("m1", "可以")
    state.mark([1], "可以", {1})
    reads = iter([{}, {"processed_message_ids": ["m1"]}])
    clock = iter([0, 21, 22])
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(clock)))

    async def no_sleep(_):
        pass

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    decision = SimpleNamespace(progress=SimpleNamespace(remaining_question_ids=[]))
    monkeypatch.setattr(module.VoiceTurnGuard, "build_recovery_decision", lambda *_: decision)
    session = SimpleNamespace(
        closed=False,
        progress_sync_version=1,
        session_no="synthetic",
        redis=SimpleNamespace(get=lambda _: next(reads)),
        provisional=state,
        task_list=[],
    )
    gateway = module.VoiceGateway()
    refresh = AsyncMock()
    monkeypatch.setattr(gateway, "_refresh_conversation_scope", refresh)
    await gateway._sync_progress(session, 1)
    assert refresh.await_count == 3
    assert not state.pending


@pytest.mark.asyncio
async def test_initial_tool_wait_does_not_block_upstream_event_consumer(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.services.voice_gateway import VOICE_HEARD_TOOL_NAME, VoiceGateway

    gate = asyncio.Event()
    entered = asyncio.Event()

    async def tool(*_args, **_kwargs):
        entered.set()
        await gate.wait()

    gateway = VoiceGateway()
    monkeypatch.setattr(gateway, "_handle_tool_call", tool)
    session = SimpleNamespace(
        input_message_id="m1",
        provisional=VoiceProvisionalState(),
        provisional_tool_tasks=set(),
        session_no="synthetic",
    )
    await asyncio.wait_for(
        gateway._handle_event(
            session,
            {
                "type": "response.function_call_arguments.done",
                "name": VOICE_HEARD_TOOL_NAME,
                "call_id": "c1",
                "arguments": "{}",
            },
        ),
        timeout=1,
    )
    await entered.wait()
    assert session.provisional_tool_tasks
    gate.set()
    await asyncio.gather(*session.provisional_tool_tasks)
