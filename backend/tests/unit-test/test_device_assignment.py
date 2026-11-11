from sqlalchemy.dialects import postgresql

from app.models.patient_task import CareTask
from app.schemas.task import BackendTaskDto


def test_device_assignment_is_exclusive_for_active_tasks():
    index = next(i for i in CareTask.__table__.indexes if i.name == "uq_care_task_active_device")
    assert index.unique
    assert list(index.columns.keys()) == ["device_id"]
    condition = str(index.dialect_options["postgresql"]["where"].compile(dialect=postgresql.dialect()))
    assert "in_progress" in condition and "deleted = 0" in condition


def test_task_response_exposes_device_assignment():
    assert "device_id" in BackendTaskDto.model_fields
