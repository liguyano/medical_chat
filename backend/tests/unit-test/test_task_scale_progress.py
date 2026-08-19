"""目标量表进度状态测试。"""

from app.services.task_service import _resolve_scale_progress_status


def test_completed_scale_uses_real_answer_progress():
    assert (
        _resolve_scale_progress_status(
            total=6,
            answered=6,
            task_status="in_progress",
            collecting_assigned=False,
        )
        == "completed"
    )


def test_only_one_incomplete_scale_is_collecting():
    assert (
        _resolve_scale_progress_status(
            total=6,
            answered=3,
            task_status="in_progress",
            collecting_assigned=False,
        )
        == "collecting"
    )
    assert (
        _resolve_scale_progress_status(
            total=5,
            answered=0,
            task_status="in_progress",
            collecting_assigned=True,
        )
        == "pending"
    )
