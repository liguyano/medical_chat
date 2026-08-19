"""工具领域事件与 SSE 映射单元测试。"""

import json

from app.schemas.events import (
    ConsentTriggeredEvent,
    EducationTriggeredEvent,
    HandoffRequestedEvent,
)
from app.services.sse_service import format_sse_event


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
    )
    formatted = format_sse_event("1-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert formatted["event"] == "education_triggered"
    assert envelope["payload"]["original_content"] == "宣教原文"
    assert envelope["payload"]["auto_play"] is True


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
    )
    formatted = format_sse_event("2-0", _fields(event))
    envelope = json.loads(formatted["data"])
    assert formatted["event"] == "consent_triggered"
    assert envelope["payload"]["clauses"][0]["id"] == "C1"


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
