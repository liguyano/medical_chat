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
