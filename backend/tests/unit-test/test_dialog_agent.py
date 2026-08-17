"""Dialog Agent 核心编排单元测试。"""

from unittest.mock import AsyncMock

import pytest
from medagent.agents.middleware import DialogMiddleware
from medagent.agents.service_agent.dialog_agent import DialogAgent, DialogEngine
from medagent.agents.service_agent.dialog_agent.agent import GENERIC_ERROR_MESSAGE
from medagent.agents.service_agent.schedule_agent import QuestionTask


class FakeEngine(DialogEngine):
    """可控统一事件引擎。"""

    def __init__(self, events=()):
        self.events = list(events)
        self.created = None
        self.inputs = []
        self.updates = []
        self.tool_results = []
        self.closed = False

    async def create_session(self, system_prompt, tools, **kwargs):
        self.created = {"system_prompt": system_prompt, "tools": tools}

    async def send_input(self, input_data):
        self.inputs.append(input_data)

    async def stream_response(self):
        for event in self.events:
            if isinstance(event, BaseException):
                raise event
            yield event

    async def send_tool_result(self, call_id, result):
        self.tool_results.append((call_id, result))
        return False

    async def update_session(self, instructions=None, tools=None):
        self.updates.append({"instructions": instructions, "tools": tools})

    async def close_session(self):
        self.closed = True


class FakeStateStore:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def save_agent_state(self, session_id, agent_state):
        self.calls.append((session_id, agent_state))
        return self.result


class FakeHistoryStore:
    def __init__(self):
        self.calls = []

    async def save_message(self, session_no, **kwargs):
        self.calls.append((session_no, kwargs))


class CaptureMiddleware(DialogMiddleware):
    """记录上下文并按患者输入注入约束。"""

    def __init__(self):
        self.before_inputs = []
        self.after_context = None
        self.after_output = None

    async def before_agent(self, context):
        self.before_inputs.append(context["patient_input"])
        if context["patient_input"]:
            context["constraints"].append(
                f"处理患者输入：{context['patient_input']}"
            )

    async def after_agent(self, context, output):
        self.after_context = dict(context)
        self.after_output = output


def task():
    return QuestionTask(
        question_id=1,
        question_code="smoking",
        question_name="吸烟情况",
        patient_text="请问您是否吸烟？",
        question_type="单选",
        required=True,
        sort_no=1,
    )


def agent(engine, **kwargs):
    return DialogAgent(
        session_id="session",
        patient_info={"name": "张三", "age": 60},
        task_list=[task()],
        engine=engine,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_initialize_builds_prompt_registers_tools_and_saves_state():
    """初始化应创建会话并持久化可恢复状态。"""
    engine = FakeEngine()
    state = FakeStateStore()
    dialog = agent(engine, state_store=state)

    await dialog.initialize()

    assert "CICARE" in engine.created["system_prompt"]
    assert engine.created["tools"]
    assert state.calls[0][0] == "session"
    assert state.calls[0][1]["engine_type"] == "FakeEngine"


@pytest.mark.asyncio
async def test_initialize_closes_engine_when_state_save_fails():
    """预热状态无法保存时不得留下已连接引擎。"""
    engine = FakeEngine()
    dialog = agent(engine, state_store=FakeStateStore(result=False))

    with pytest.raises(RuntimeError, match="初始状态保存失败"):
        await dialog.initialize()

    assert engine.closed is True


@pytest.mark.asyncio
async def test_text_turn_applies_constraints_persists_and_publishes_context():
    """文本输入必须在 before middleware 前进入上下文。"""
    engine = FakeEngine(
        [
            {"type": "text", "content": "我理解您。"},
            {"type": "text", "content": "请问每天多少支？"},
            {"type": "response_done"},
        ]
    )
    state = FakeStateStore()
    history = FakeHistoryStore()
    middleware = CaptureMiddleware()
    dialog = agent(
        engine,
        middlewares=[middleware],
        state_store=state,
        history_store=history,
    )

    result = await dialog.handle_patient_input("我每天吸烟", session_no="S001")

    assert result == "我理解您。请问每天多少支？"
    assert middleware.before_inputs == ["我每天吸烟"]
    assert "我每天吸烟" in engine.updates[0]["instructions"]
    assert [call[1]["role_type"] for call in history.calls] == ["患者", "AI"]
    assert {call[1]["turn_no"] for call in history.calls} == {1}
    assert middleware.after_context["patient_input"] == "我每天吸烟"
    assert middleware.after_output == result
    assert state.calls[-1][1]["turn_counter"] == 1


@pytest.mark.asyncio
async def test_voice_transcript_runs_middleware_and_saves_asr():
    """语音 ASR 到达后应补跑 before middleware 并保存患者文本。"""
    engine = FakeEngine(
        [
            {"type": "user_transcript", "text": "我不吸烟"},
            {"type": "audio", "data": b"audio"},
            {"type": "text", "content": "好的"},
            {"type": "response_done"},
        ]
    )
    history = FakeHistoryStore()
    middleware = CaptureMiddleware()
    dialog = agent(engine, middlewares=[middleware], history_store=history)

    result = await dialog.handle_patient_input(b"pcm", session_no="S001")

    assert result == "好的"
    assert middleware.before_inputs == ["", "我不吸烟"]
    assert "我不吸烟" in engine.updates[0]["instructions"]
    assert history.calls[0][1]["asr_text"] == "我不吸烟"
    assert middleware.after_context["audio_chunks"] == [b"audio"]


@pytest.mark.asyncio
async def test_tool_call_executes_records_and_returns_result():
    """完整工具事件应执行、记录并回传给引擎。"""
    engine = FakeEngine(
        [
            {
                "type": "tool_call",
                "call_id": "call-1",
                "name": "get_education_material",
                "arguments": {"category": "tobacco"},
            },
            {"type": "response_done"},
        ]
    )
    tool_executor = AsyncMock(return_value={"success": True})
    middleware = CaptureMiddleware()
    dialog = agent(
        engine,
        middlewares=[middleware],
        tool_executor=tool_executor,
    )

    await dialog.handle_patient_input("我吸烟")

    tool_executor.assert_awaited_once_with(
        "get_education_material",
        {"category": "tobacco"},
    )
    assert engine.tool_results == [("call-1", {"success": True})]
    assert middleware.after_context["tool_calls"][0]["name"] == (
        "get_education_material"
    )


@pytest.mark.asyncio
async def test_text_tool_call_continues_until_patient_facing_answer():
    """需后续模型调用的引擎应在工具结果后继续读取最终回答。"""

    class FollowupEngine(FakeEngine):
        def __init__(self):
            super().__init__()
            self.rounds = [
                [
                    {
                        "type": "tool_call",
                        "call_id": "call-1",
                        "name": "trigger_consent_form",
                        "arguments": {"form_type": "surgery"},
                    },
                    {"type": "response_done"},
                ],
                [
                    {"type": "text", "content": "手术知情同意书已准备，请您阅读。"},
                    {"type": "response_done"},
                ],
            ]

        async def stream_response(self):
            for event in self.rounds.pop(0):
                yield event

        async def send_tool_result(self, call_id, result):
            self.tool_results.append((call_id, result))
            return True

    engine = FollowupEngine()
    dialog = agent(
        engine,
        tool_executor=AsyncMock(
            return_value={"success": True, "status": "pending_signature"}
        ),
    )

    result = await dialog.handle_patient_input("我明天要做手术")

    assert result == "手术知情同意书已准备，请您阅读。"
    assert len(engine.tool_results) == 1


@pytest.mark.asyncio
async def test_broken_tool_event_is_ignored():
    """缺少 call_id 或 arguments 的事件不得执行工具。"""
    engine = FakeEngine(
        [
            {"type": "tool_call", "name": "tool", "arguments": {}},
            {"type": "response_done"},
        ]
    )
    tool_executor = AsyncMock()
    dialog = agent(engine, tool_executor=tool_executor)

    await dialog.handle_patient_input("输入")

    tool_executor.assert_not_awaited()
    assert engine.tool_results == []


@pytest.mark.asyncio
async def test_tool_failure_is_returned_as_structured_result():
    """工具异常应降级为失败结果，不中断当前轮次。"""
    engine = FakeEngine(
        [
            {
                "type": "tool_call",
                "call_id": "call-1",
                "name": "tool",
                "arguments": {},
            },
            {"type": "text", "content": "继续评估"},
            {"type": "response_done"},
        ]
    )
    tool_executor = AsyncMock(side_effect=RuntimeError("tool failed"))
    dialog = agent(engine, tool_executor=tool_executor)

    result = await dialog.handle_patient_input("输入")

    assert result == "继续评估"
    assert engine.tool_results[0][1]["success"] is False


@pytest.mark.asyncio
async def test_engine_error_and_exception_use_generic_patient_message():
    """供应商错误不得原样暴露给患者。"""
    error_agent = agent(
        FakeEngine([{"type": "error", "message": "secret upstream"}])
    )
    exception_agent = agent(FakeEngine([RuntimeError("secret traceback")]))

    error_result = await error_agent.handle_patient_input("输入")
    exception_result = await exception_agent.handle_patient_input("输入")

    assert error_result == GENERIC_ERROR_MESSAGE
    assert exception_result == GENERIC_ERROR_MESSAGE
    assert "secret" not in error_result
    assert "secret" not in exception_result


@pytest.mark.asyncio
async def test_close_releases_engine():
    """Dialog Agent close 应委托底层引擎释放资源。"""
    engine = FakeEngine()
    dialog = agent(engine)

    await dialog.close()

    assert engine.closed is True
