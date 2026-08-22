"""Agent 非阻塞派发服务测试。"""

from types import SimpleNamespace
from unittest.mock import Mock


def test_session_agent_payload_contains_only_current_diagnosis_context():
    """Agent payload 应包含当前诊断，不应混入本次明确排除的住院字段。"""
    from datetime import date

    import app.services.agent_dispatch_service as service
    from app.models.patient_task import CareTask, Patient, PatientEncounter

    class ScalarRows:
        def all(self):
            return ["COPD"]

    class FakeDb:
        def __init__(self):
            self.rows = {
                CareTask: SimpleNamespace(id=1, task_no="TASK-1"),
                Patient: SimpleNamespace(
                    id=2,
                    patient_name="患者",
                    sex="男",
                    birthday=date(1960, 1, 1),
                ),
                PatientEncounter: SimpleNamespace(
                    id=3,
                    department_name="呼吸科",
                    bed_no="01",
                    diagnosis_snapshot={"primary": "慢性阻塞性肺疾病急性加重"},
                    allergy_summary="不纳入 Agent 上下文",
                    admission_source="急诊",
                    nursing_level="一级护理",
                ),
            }

        def get(self, model, _id):
            return self.rows[model]

        def scalars(self, _query):
            return ScalarRows()

    patient_info, task_config = service.build_session_agent_payload(
        FakeDb(),
        SimpleNamespace(task_id=1, patient_id=2, encounter_id=3),
    )

    assert patient_info["diagnosis_snapshot"] == {
        "primary": "慢性阻塞性肺疾病急性加重"
    }
    assert "allergy_summary" not in patient_info
    assert "admission_source" not in patient_info
    assert "nursing_level" not in patient_info
    assert task_config["scale_codes"] == ["COPD"]


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
