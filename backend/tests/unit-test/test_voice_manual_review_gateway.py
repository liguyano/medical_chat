"""固定人工审核结束播报的 Voice Gateway 测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.voice_gateway as voice_gateway_module
from app.services.voice_gateway import VoiceGateway


@pytest.mark.asyncio
async def test_finish_recovery_mode_with_manual_review_creates_dedicated_response(monkeypatch):
    """remaining 清空后，存在固定人工审核项时必须主动创建专门结束播报。"""
    gateway = VoiceGateway()
    client = SimpleNamespace(
        update_instructions=AsyncMock(),
        create_response=AsyncMock(),
    )
    session = SimpleNamespace(
        session_no="SESS-MANUAL",
        patient_info={"name": "患者", "manual_review_count": 2},
        client=client,
        closed=False,
        speech_active=False,
        responding=False,
        active_response_ids=set(),
        pending_tool_responses=0,
        response_requested=False,
        recovery_instruction_active=True,
        recovery_mode_active=True,
        recovery_current_question_id=25,
        recovery_source_message_no="MSG-PATIENT-4",
        recovery_answer_response_pending=False,
        next_response_is_recovery=False,
        next_response_is_manual_review_completion=False,
    )
    notify = Mock(
        return_value=SimpleNamespace(
            item_count=2,
            notified=True,
            request_id="MANUAL-REVIEW-1",
        )
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "ensure_planned_manual_review_notification",
        notify,
        raising=False,
    )

    await gateway._finish_recovery_mode(session)

    notify.assert_called_once_with("SESS-MANUAL")
    client.update_instructions.assert_awaited_once()
    prompt = client.update_instructions.await_args.args[0]
    assert "人工审核" in prompt
    assert "护士" in prompt
    assert "已通知" in prompt
    client.create_response.assert_awaited_once()
    assert session.response_requested is True
    assert session.next_response_is_manual_review_completion is True
    assert session.recovery_mode_active is False


@pytest.mark.asyncio
async def test_manual_review_followup_announces_after_normal_response_when_extraction_finishes(monkeypatch):
    """非恢复模式最后一轮 response.done 早于 Extraction 时，也要在抽取完成后补播报。"""
    gateway = VoiceGateway()
    client = SimpleNamespace(
        update_instructions=AsyncMock(),
        create_response=AsyncMock(),
    )
    session = SimpleNamespace(
        session_no="SESS-NORMAL-LAST",
        patient_info={"name": "患者", "manual_review_count": 2},
        task_list=[],
        client=client,
        redis=object(),
        closed=False,
        speech_active=False,
        responding=False,
        active_response_ids=set(),
        pending_tool_responses=0,
        response_requested=False,
        manual_review_completion_task=None,
        next_response_is_manual_review_completion=False,
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "latest_patient_message_no",
        lambda _session_no: "MSG-PATIENT-LAST",
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "extraction_processed",
        lambda _redis, _session_no, _message_no: True,
    )
    monkeypatch.setattr(
        voice_gateway_module.VoiceTurnGuard,
        "build_recovery_decision",
        lambda _session_no, _tasks: SimpleNamespace(
            progress=SimpleNamespace(completed=True, remaining_question_ids=()),
            should_recover=False,
            next_question=None,
        ),
    )
    notify = Mock(
        return_value=SimpleNamespace(
            item_count=2,
            notified=True,
            request_id="MANUAL-REVIEW-1",
        )
    )
    monkeypatch.setattr(
        voice_gateway_module,
        "ensure_planned_manual_review_notification",
        notify,
        raising=False,
    )

    await gateway._announce_manual_review_after_extraction(session)

    notify.assert_called_once_with("SESS-NORMAL-LAST")
    client.create_response.assert_awaited_once()
    assert session.next_response_is_manual_review_completion is True
