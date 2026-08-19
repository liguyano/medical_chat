"""工具领域事件与 SSE 映射单元测试。"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from app.schemas.events import (
    ConsentTriggeredEvent,
    EducationTriggeredEvent,
    HandoffRequestedEvent,
)
from app.services.sse_service import format_sse_event
from app.services.tool_interaction_service import (
    _interaction_event_payload,
    _resolve_pending_handoff_rows,
)


def _fields(event) -> dict[bytes, bytes]:
    """模拟 Redis Stream 发布后的 bytes 字段。"""
    raw = event.model_dump(mode="json")
    return {
        str(key).encode(): (
            json.dumps(value, ensure_ascii=False).encode()
            if isinstance(value, (dict, list))
            else str(value).encode()
        )
        for key, value in raw.items()
        if value is not None
    }


def test_education_event_maps_to_frontend_payload():
    """宣教事件应保留原文、播报文本和自动播放标记。"""
    event = EducationTriggeredEvent(
        session_id="SESS-1",
        task_id=1,
        material_id="EDU-1",
        category="allergy",
        level=3,
        document_version="1.0",
        title="药物过敏安全宣教",
        original_content="宣教原文",
        patient_content="通俗说明",
        spoken_content="播报内容",
        auto_play=True,
        tool_name="get_education_material",
        tool_args={"category": "allergy"},
        tool_result={"success": True, "material_id": "EDU-1"},
    )
    formatted = format_sse_event("1-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert formatted["event"] == "education_triggered"
    assert envelope["payload"]["original_content"] == "宣教原文"
    assert envelope["payload"]["auto_play"] is True
    assert envelope["payload"]["tool_name"] == "get_education_material"
    assert envelope["payload"]["tool_result"]["material_id"] == "EDU-1"


def test_consent_event_maps_clauses():
    """知情同意事件应向前端传输结构化条款。"""
    event = ConsentTriggeredEvent(
        session_id="SESS-1",
        task_id=1,
        form_id="FORM-1",
        form_type="surgery",
        title="手术知情同意提醒",
        document_version="1.0",
        full_text="完整文本",
        clauses=[{"id": "C1", "patient_content": "条款内容"}],
        tool_name="trigger_consent_form",
        tool_args={"form_type": "surgery"},
        tool_result={"success": True, "form_id": "FORM-1"},
    )
    formatted = format_sse_event("2-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert formatted["event"] == "consent_triggered"
    assert envelope["payload"]["clauses"][0]["id"] == "C1"
    assert envelope["payload"]["tool_name"] == "trigger_consent_form"


def test_handoff_event_maps_patient_and_action():
    """医护呼叫事件应包含患者、床位、原因和请求操作。"""
    event = HandoffRequestedEvent(
        session_id="SESS-1",
        task_id=1,
        request_id="NURSE-1",
        reason="需要测量血压",
        requested_action="measure_blood_pressure",
        action_label="测量血压",
        patient_name="张三",
        bed_no="08床",
    )
    formatted = format_sse_event("3-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert formatted["event"] == "handoff_requested"
    assert envelope["payload"]["patient_name"] == "张三"
    assert envelope["payload"]["action_label"] == "测量血压"


def test_agent_handoff_event_keeps_tool_result_and_source():
    """Agent 呼叫应区分来源，并保留工具参数与完整结果。"""
    event = HandoffRequestedEvent(
        session_id="SESS-1",
        task_id=1,
        message_id="MSG-PATIENT-1",
        request_id="NURSE-1",
        reason="患者需要测量血压",
        requested_action="measure_blood_pressure",
        action_label="测量血压",
        patient_name="张三",
        bed_no="08床",
        request_source="agent",
        tool_name="request_nurse_assistance",
        tool_args={
            "requested_action": "measure_blood_pressure",
            "reason": "患者需要测量血压",
        },
        tool_result={
            "success": True,
            "request_id": "NURSE-1",
            "status": "requested",
        },
    )
    formatted = format_sse_event("4-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert envelope["payload"]["request_source"] == "agent"
    assert envelope["payload"]["tool_name"] == "request_nurse_assistance"
    assert envelope["payload"]["tool_result"]["request_id"] == "NURSE-1"


def test_handoff_resolved_event_keeps_staff_identity_and_batch_ids():
    """处理结果应包含护士身份、处理时间和本次关闭的请求编号。"""
    from app.schemas.events import HandoffResolvedEvent

    event = HandoffResolvedEvent(
        session_id="SESS-1",
        task_id=1,
        request_id="NURSE-2",
        request_ids=["NURSE-1", "NURSE-2"],
        resolved_by_staff_id="1",
        resolved_by_staff_no="N001",
        resolved_by_name="李护士",
        handled_at="2026-08-19T12:00:00Z",
        resolution="已完成血压测量",
    )
    formatted = format_sse_event("5-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert envelope["payload"]["request_ids"] == ["NURSE-1", "NURSE-2"]
    assert envelope["payload"]["resolved_by_staff_no"] == "N001"
    assert envelope["payload"]["resolved_by_name"] == "李护士"
    assert envelope["payload"]["remaining_pending"] is False


def test_resolve_handoff_rows_closes_all_pending_requests():
    """未指定 request_id 时应一次关闭当前任务全部待处理呼叫。"""
    rows = [
        SimpleNamespace(
            event_payload={"request_id": "NURSE-1", "status": "requested"},
            handled_status="pending",
            handled_by=None,
            handled_at=None,
            updator=None,
        ),
        SimpleNamespace(
            event_payload={"request_id": "NURSE-2", "status": "requested"},
            handled_status="pending",
            handled_by=None,
            handled_at=None,
            updator=None,
        ),
    ]
    handled_at = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    request_ids = _resolve_pending_handoff_rows(
        rows,
        request_id=None,
        staff_id=1,
        staff_no="N001",
        staff_name="李护士",
        handled_at=handled_at,
        resolution="均已处理",
    )
    assert request_ids == ["NURSE-1", "NURSE-2"]
    assert all(row.handled_status == "resolved" for row in rows)
    assert all(row.event_payload["resolved_by_staff_no"] == "N001" for row in rows)
    assert all(row.event_payload["handled_at"] == handled_at.isoformat() for row in rows)


def test_interaction_event_payload_keeps_resolved_event_handled_at():
    """处理结果事件未填写列时间时，不应覆盖 payload 中的真实处理时间。"""
    row = SimpleNamespace(
        event_payload={
            "request_ids": ["NURSE-1"],
            "handled_at": "2026-08-19T12:00:00+00:00",
            "resolved_by_staff_no": "N001",
        },
        handled_status="resolved",
        handled_by="1",
        handled_at=None,
    )

    payload = _interaction_event_payload(row)

    assert payload["handled_at"] == "2026-08-19T12:00:00+00:00"
    assert payload["handled_status"] == "resolved"
    assert payload["handled_by"] == "1"
