from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services.device_registry import approve_registration


def test_approval_requires_the_current_verification_code():
    row = SimpleNamespace(
        verification_code="AB12CD34", expires_at=datetime.now(UTC) + timedelta(minutes=1),
        approved_at=None, approved_by=None,
    )
    db = Mock()
    db.scalar.return_value = row
    with pytest.raises(HTTPException) as error:
        approve_registration(db, "ESP32-001", "11111111", staff_id=7)
    assert error.value.status_code == 409
    db.commit.assert_not_called()

    approve_registration(db, "ESP32-001", "AB12CD34", staff_id=7)
    assert row.approved_at is not None
    assert row.approved_by == 7
    db.commit.assert_called_once()
