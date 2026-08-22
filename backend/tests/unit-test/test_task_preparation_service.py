"""AI 首问准备状态服务单元测试。"""

from types import SimpleNamespace

from app.services.task_preparation_service import (
    PREPARATION_STAGES,
    initialize_ai_preparation,
    initialize_traditional_preparation,
    mark_stage_completed,
    mark_stage_failure,
    mark_stage_running,
    preparation_payload,
    reset_for_retry,
)


def test_ai_preparation_starts_hidden_and_queued():
    """AI 任务初始化后必须处于准备中且患者不可见。"""
    task = SimpleNamespace()

    initialize_ai_preparation(task)

    assert task.preparation_status == "queued"
    assert task.preparation_stage == "schedule_prepare"
    assert task.patient_visible_at is None
    assert list(task.preparation_detail["stages"]) == list(PREPARATION_STAGES)


def test_traditional_preparation_is_visible_without_agent_pipeline():
    """传统问卷不需要首问准备，创建后可直接发布。"""
    from datetime import UTC, datetime

    task = SimpleNamespace()
    visible_at = datetime.now(UTC)

    initialize_traditional_preparation(task, visible_at)

    assert task.preparation_status == "not_required"
    assert task.patient_visible_at == visible_at
    assert task.preparation_detail is None


def test_preparation_payload_contains_stage_outputs_and_retry_count():
    """医护端 DTO 载荷应保留阶段输出和重试次数。"""
    task = SimpleNamespace(
        collection_mode="ai_dialogue",
        preparation_status="failed",
        preparation_stage="dialog_opening",
        preparation_attempt=2,
        preparation_error="模型失败",
        patient_visible_at=None,
        preparation_detail={
            "stages": {
                "dialog_opening": {
                    "status": "failed",
                    "output": {"content": "部分文本"},
                    "error": "模型失败",
                    "updated_at": "2026-08-22T00:00:00Z",
                }
            }
        },
    )

    payload = preparation_payload(task)

    assert payload["status"] == "failed"
    assert payload["attempt"] == 2
    assert payload["stages"]["dialog_opening"]["output"]["content"] == "部分文本"


def test_retry_resets_pipeline_and_keeps_attempt_count():
    """失败任务重试时恢复队列状态并递增尝试次数。"""
    task = SimpleNamespace(
        preparation_status="failed",
        preparation_stage="dialog_opening",
        preparation_error="模型失败",
        preparation_attempt=1,
        preparation_detail={"stages": {}},
        patient_visible_at=None,
    )

    reset_for_retry(None, task)

    assert task.preparation_status == "queued"
    assert task.preparation_stage == "schedule_prepare"
    assert task.preparation_attempt == 2
    assert task.preparation_error is None


def test_stage_transitions_publish_ready_only_after_opening(monkeypatch):
    """只有首问阶段完成后任务才允许患者可见。"""
    import app.services.task_preparation_service as service

    class FakeDb:
        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    task = SimpleNamespace(collection_mode="ai_dialogue")
    initialize_ai_preparation(task)
    fake_db = FakeDb()
    monkeypatch.setattr(service.model_base, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(service, "_load_task", lambda _db, _session: task)

    assert mark_stage_running("SESS-1", "schedule_prepare")
    assert mark_stage_completed(
        "SESS-1",
        "schedule_prepare",
        output={"question_count": 2},
    )
    assert task.patient_visible_at is None
    assert mark_stage_completed(
        "SESS-1",
        "dialog_preheat",
        output={"question_count": 2},
    )
    assert task.patient_visible_at is None
    assert mark_stage_completed(
        "SESS-1",
        "dialog_opening",
        output={"content": "您好，请问您现在感觉如何？"},
    )
    assert task.preparation_status == "ready"
    assert task.patient_visible_at is not None


def test_final_stage_failure_keeps_task_hidden(monkeypatch):
    """最终准备失败时患者可见时间必须保持为空。"""
    import app.services.task_preparation_service as service

    class FakeDb:
        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    task = SimpleNamespace(collection_mode="ai_dialogue")
    initialize_ai_preparation(task)
    fake_db = FakeDb()
    monkeypatch.setattr(service.model_base, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(service, "_load_task", lambda _db, _session: task)

    assert mark_stage_failure(
        "SESS-1",
        "dialog_opening",
        reason="模型不可用",
        retrying=False,
    )
    assert task.preparation_status == "failed"
    assert task.patient_visible_at is None
