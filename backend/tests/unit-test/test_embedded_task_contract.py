"""嵌入式设备任务创建契约。"""

import pytest
from pydantic import ValidationError

from app.schemas.task import CreateTaskRequest


TASK = {"patient_id": 1, "encounter_id": 2, "scale_ids": [3]}


def test_embedded_task_requires_device_id():
    with pytest.raises(ValidationError):
        CreateTaskRequest(**TASK, collection_mode="embedded_device")

    task = CreateTaskRequest(
        **TASK, collection_mode="embedded_device", device_id="ESP32-001"
    )
    assert task.device_id == "ESP32-001"


@pytest.mark.parametrize("mode", ["traditional_form", "ai_dialogue"])
def test_other_task_modes_reject_device_id(mode):
    assert CreateTaskRequest(**TASK, collection_mode=mode).device_id is None
    with pytest.raises(ValidationError):
        CreateTaskRequest(**TASK, collection_mode=mode, device_id="ESP32-001")
