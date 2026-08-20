"""Agent 非阻塞派发服务测试。"""

from types import SimpleNamespace
from unittest.mock import Mock


def test_answer_dispatch_does_not_chain_background_agents(monkeypatch):
    """Dialog 应立即独立派发，后台 Agent 不得成为前置依赖。"""
    import app.services.agent_dispatch_service as service
    from app.celery_app import tasks

    monkeypatch.setattr(
        service,
        "build_session_agent_payload",
        lambda _db, _session: (
            {"name": "患者"},
            {"task_id": 1, "scale_codes": ["scale"]},
        ),
    )
    dialog_delay = Mock()
    schedule_delay = Mock()
    extraction_delay = Mock()
    monkeypatch.setattr(tasks.dialog_agent_worker, "delay", dialog_delay)
    monkeypatch.setattr(tasks.schedule_agent_worker, "delay", schedule_delay)
    monkeypatch.setattr(tasks.extraction_agent_worker, "delay", extraction_delay)

    service.dispatch_answer_workers(
        object(),
        SimpleNamespace(session_no="SESS-1"),
        source_message_id="PATIENT-1",
        source_event_id="1-0",
    )

    assert dialog_delay.call_count == 1
    assert schedule_delay.call_count == 1
    assert extraction_delay.call_count == 1


def test_background_dispatch_failure_does_not_block_dialog(monkeypatch):
    """Schedule/Extraction 入队失败不得让已接受的患者消息失败。"""
    import app.services.agent_dispatch_service as service
    from app.celery_app import tasks

    monkeypatch.setattr(
        service,
        "build_session_agent_payload",
        lambda _db, _session: (
            {"name": "患者"},
            {"task_id": 1, "scale_codes": ["scale"]},
        ),
    )
    dialog_delay = Mock()
    monkeypatch.setattr(tasks.dialog_agent_worker, "delay", dialog_delay)
    monkeypatch.setattr(
        tasks.schedule_agent_worker,
        "delay",
        Mock(side_effect=RuntimeError("schedule unavailable")),
    )
    monkeypatch.setattr(
        tasks.extraction_agent_worker,
        "delay",
        Mock(side_effect=RuntimeError("extraction unavailable")),
    )

    service.dispatch_answer_workers(
        object(),
        SimpleNamespace(session_no="SESS-1"),
        source_message_id="PATIENT-1",
        source_event_id="1-0",
    )

    dialog_delay.assert_called_once()


def test_voice_dispatch_skips_text_dialog_agent(monkeypatch):
    """语音模型已经生成 AI 回复，语音轮次不得再次派发文本 Dialog。"""
    import app.services.agent_dispatch_service as service
    from app.celery_app import tasks

    dialog_delay = Mock()
    schedule_delay = Mock()
    extraction_delay = Mock()
    monkeypatch.setattr(tasks.dialog_agent_worker, "delay", dialog_delay)
    monkeypatch.setattr(tasks.schedule_agent_worker, "delay", schedule_delay)
    monkeypatch.setattr(tasks.extraction_agent_worker, "delay", extraction_delay)

    service.dispatch_voice_answer_workers(
        "SESS-VOICE",
        task_id=1,
        scale_codes=["scale"],
        source_message_id="PATIENT-VOICE-1",
        source_event_id=None,
        patient_info={"name": "患者"},
    )

    dialog_delay.assert_not_called()
    schedule_delay.assert_called_once()
    extraction_delay.assert_called_once()
    assert schedule_delay.call_args.args[0] == "SESS-VOICE"
