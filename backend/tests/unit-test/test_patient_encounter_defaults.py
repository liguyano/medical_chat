from datetime import UTC, datetime

from app.schemas.patient import PatientEncounterCreatePayload


def test_encounter_automatically_fills_unused_fields_and_unique_number() -> None:
    fields = {"department_name": "测试科室", "ward_name": "测试病区"}
    first = PatientEncounterCreatePayload(**fields)
    second = PatientEncounterCreatePayload(**fields)
    assert first.inpatient_no.startswith("ZY-")
    assert first.inpatient_no != second.inpatient_no
    assert first.bed_no == "待分配"
    assert first.nursing_level == "待评定"
    assert first.admission_source == "未登记"


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
