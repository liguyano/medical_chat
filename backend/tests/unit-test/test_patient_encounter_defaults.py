from datetime import UTC, datetime

from app.schemas.patient import PatientEncounterCreatePayload


def test_encounter_defaults_to_current_time_and_in_hospital() -> None:
    before = datetime.now(UTC)
    encounter = PatientEncounterCreatePayload(
        inpatient_no="TEST-AUTO-TIME", department_name="测试科室",
        ward_name="测试病区", bed_no="TEST-1",
    )
    after = datetime.now(UTC)
    assert before <= encounter.admission_time <= after
    assert encounter.discharge_time is None
    assert encounter.encounter_status == "在院"


def test_explicit_historical_admission_time_is_preserved() -> None:
    historical = datetime(2020, 1, 2, 8, tzinfo=UTC)
    encounter = PatientEncounterCreatePayload(
        inpatient_no="TEST-HISTORY", department_name="测试科室",
        ward_name="测试病区", bed_no="TEST-2", admission_time=historical,
    )
    assert encounter.admission_time == historical
