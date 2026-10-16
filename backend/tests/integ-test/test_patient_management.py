"""医护端患者管理接口集成测试。

前置条件：按 deploy/Install.md 启动 PostgreSQL、Redis，并执行 Alembic 升级。
"""

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models import base as model_base
from app.models.patient_task import Patient, PatientEncounter


def test_staff_can_create_search_view_and_update_patient() -> None:
    """医护会话应完成患者主档与住院记录的一体化管理。"""
    suffix = uuid.uuid4().hex[:10]
    patient_id: int | None = None
    encounter_id: int | None = None
    payload = {
        "patient": {
            "his_patient_id": f"HIS-CODEX-{suffix}",
            "patient_name": "接口测试患者",
            "sex": "女",
            "birthday": "1988-08-08",
            "id_card_no": f"CODEX-ID-{suffix}",
            "phone": f"138{suffix[:8]}",
            "emergency_contact_name": "测试家属",
            "emergency_contact_relation": "女儿",
            "emergency_contact_phone": f"139{suffix[:8]}",
            "address": "接口测试地址",
        },
        "encounter": {
            "department_code": "CARD",
            "department_name": "心内科",
            "ward_name": "心内病区A",
            "diagnosis_snapshot": {
                "primary": "冠心病",
                "secondary": ["高血压"],
                "risk_note": "注意跌倒",
            },
            "insurance_type": "城镇职工医保",
            "allergy_summary": "青霉素过敏",
        },
    }

    with TestClient(app) as client:
        try:
            login = client.post(
                "/api/auth/staff/login",
                json={"staff_no": "N001", "password": "123456"},
            )
            assert login.status_code == 200, login.text

            before_create = datetime.now(UTC)
            created = client.post("/api/patients", json=payload)
            assert created.status_code == 200, created.text
            created_data = created.json()["data"]
            patient_id = int(created_data["patient"]["id"])
            encounter_id = int(created_data["encounter"]["id"])
            assert model_base.SessionLocal is not None
            with model_base.SessionLocal() as verification_db:
                saved_patient = verification_db.get(Patient, patient_id)
                saved_encounter = verification_db.get(PatientEncounter, encounter_id)
                assert saved_patient is not None
                assert saved_patient.patient_name == "接口测试患者"
                assert saved_encounter is not None
                assert saved_encounter.patient_id == saved_patient.id
                assert before_create <= saved_encounter.admission_time <= datetime.now(UTC)
                assert saved_encounter.discharge_time is None
                assert saved_encounter.encounter_status == "在院"
                saved_admission_time = saved_encounter.admission_time
                saved_inpatient_no = saved_encounter.inpatient_no
                assert saved_inpatient_no.startswith("ZY-")
                assert saved_encounter.bed_no == "待分配"
                assert saved_encounter.nursing_level == "待评定"
                assert saved_encounter.admission_source == "未登记"
            assert created_data["patient"]["id_card_masked"]
            assert "id_card_no" not in created_data["patient"]
            assert "id_card_ciphertext" not in created_data["patient"]
            assert created_data["encounter"]["allergy_summary"] == "青霉素过敏"

            listed = client.get(
                "/api/patients",
                params={"keyword": f"HIS-CODEX-{suffix}", "status": "在院"},
            )
            assert listed.status_code == 200, listed.text
            assert [item["patient"]["id"] for item in listed.json()["data"]] == [
                patient_id
            ]

            detail = client.get(f"/api/patients/{patient_id}")
            assert detail.status_code == 200, detail.text
            assert detail.json()["data"]["patient"]["patient_name"] == "接口测试患者"

            update_payload = {
                "patient": {
                    **{
                        key: value
                        for key, value in payload["patient"].items()
                        if key != "id_card_no"
                    },
                    "patient_name": "接口测试患者已编辑",
                },
                "encounter": {
                    **payload["encounter"],
                    "id": encounter_id,
                },
            }
            updated = client.put(
                f"/api/patients/{patient_id}",
                json=update_payload,
            )
            assert updated.status_code == 200, updated.text
            updated_data = updated.json()["data"]
            assert updated_data["patient"]["patient_name"] == "接口测试患者已编辑"
            assert updated_data["encounter"]["bed_no"] == "待分配"
            assert updated_data["encounter"]["nursing_level"] == "待评定"
            with model_base.SessionLocal() as verification_db:
                saved_encounter = verification_db.get(PatientEncounter, encounter_id)
                assert saved_encounter is not None
                assert saved_encounter.admission_time == saved_admission_time
                assert saved_encounter.discharge_time is None
                assert saved_encounter.inpatient_no == saved_inpatient_no
                assert saved_encounter.bed_no == "待分配"
                assert saved_encounter.nursing_level == "待评定"
                assert saved_encounter.admission_source == "未登记"

            duplicate = client.post("/api/patients", json=payload)
            assert duplicate.status_code == 409, duplicate.text
        finally:
            if model_base.SessionLocal is not None:
                with model_base.SessionLocal() as db:
                    if encounter_id is not None:
                        encounter = db.get(PatientEncounter, encounter_id)
                        if encounter is not None:
                            db.delete(encounter)
                            db.flush()
                    if patient_id is not None:
                        patient = db.get(Patient, patient_id)
                        if patient is not None:
                            db.delete(patient)
                    db.commit()
