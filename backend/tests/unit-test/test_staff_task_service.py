"""医护历史任务查询测试。"""

from app.services import task_service


def test_list_staff_tasks_filters_current_assignee_and_keeps_history(monkeypatch):
    captured = {}

    class FakeScalars:
        def all(self):
            return ["task-109"]

    class FakeDb:
        def scalars(self, statement):
            captured["statement"] = statement
            return FakeScalars()

    monkeypatch.setattr(
        task_service,
        "_to_backend_task_dto",
        lambda _db, task: {"task": task},
    )

    result = task_service.list_staff_tasks(FakeDb(), staff_id=1)
    sql = str(captured["statement"])

    assert result == [{"task": "task-109"}]
    assert "assigned_nurse_id" in sql
    assert "deleted" in sql
    assert "update_time" in sql


def test_list_patient_tasks_requires_ready_ai_release(monkeypatch):
    """患者任务查询必须同时检查 AI 已 ready 且已经发布。"""
    captured = {}

    class FakeScalars:
        def all(self):
            return ["task-110"]

    class FakeDb:
        def scalars(self, statement):
            captured["statement"] = statement
            return FakeScalars()

    monkeypatch.setattr(
        task_service,
        "_to_backend_task_dto",
        lambda _db, task: {"task": task},
    )

    result = task_service.list_patient_tasks(
        FakeDb(),
        patient_id=1,
        encounter_id=2,
    )
    sql = str(captured["statement"])

    assert result == [{"task": "task-110"}]
    assert "patient_visible_at" in sql
    assert "preparation_status" in sql


def test_retry_task_preparation_locks_task_row(monkeypatch):
    """同一失败任务并发重试时应由行锁保护状态检查和入队。"""
    from types import SimpleNamespace

    task = SimpleNamespace(
        id=1,
        task_no="TASK-1",
        deleted=0,
        assigned_nurse_id=7,
        collection_mode="ai_dialogue",
        preparation_status="failed",
        preparation_attempt=1,
        preparation_detail={"stages": {}},
        patient_visible_at=None,
    )
    session = SimpleNamespace(
        task_id=1,
        deleted=0,
        session_status="active",
        ended_at="old",
        updator="old",
    )
    statements = []

    class FakeDb:
        def scalar(self, statement):
            statements.append(statement)
            return task if len(statements) == 1 else session

        def commit(self):
            return None

        def refresh(self, _item):
            return None

    monkeypatch.setattr(
        task_service,
        "_to_backend_task_dto",
        lambda _db, item: item,
    )
    monkeypatch.setattr(
        "app.services.agent_dispatch_service.dispatch_opening_workers",
        lambda _db, _session: None,
    )

    result = task_service.retry_task_preparation(
        FakeDb(),
        "TASK-1",
        staff_id=7,
    )

    assert result is task
    assert statements[0]._for_update_arg is not None
    assert task.preparation_status == "queued"
    assert task.preparation_attempt == 2
