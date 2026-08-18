"""演示患者种子导入器
作用：幂等写入 5 位在院患者、身份凭据及住院记录，供前后端联调使用。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.configs.app_config import get_app_config
from app.models import base as model_base
from app.models.patient_task import Patient, PatientEncounter
from app.utils.patient_identity import encrypt_id_card

logger = logging.getLogger(__name__)

PATIENT_SEEDS: list[dict] = [
    {
        "patient_no": "P-DEMO-0001",
        "patient_name": "张桂芳",
        "sex": "女",
        "birthday": "1948-03-12",
        "id_card": "110101194803120010",
        "phone": "13800000001",
        "encounter_no": "E-DEMO-0001",
        "inpatient_no": "ZY0001",
        "department_code": "GERI",
        "department_name": "老年医学科",
        "ward_name": "老年科一病区",
        "bed_no": "12-1",
        "admission_offset_days": 2,
        "diagnosis_snapshot": {
            "primary": "高血压3级（很高危）",
            "secondary": ["陈旧性脑梗死", "骨质疏松"],
            "risk_note": "高龄、步态不稳、既往跌倒史，跌倒风险高",
        },
    },
    {
        "patient_no": "P-DEMO-0002",
        "patient_name": "李国强",
        "sex": "男",
        "birthday": "1955-07-25",
        "id_card": "110101195507250026",
        "phone": "13800000002",
        "encounter_no": "E-DEMO-0002",
        "inpatient_no": "ZY0002",
        "department_code": "GAST",
        "department_name": "消化内科",
        "ward_name": "消化内科病区",
        "bed_no": "08-2",
        "admission_offset_days": 3,
        "diagnosis_snapshot": {
            "primary": "胃恶性肿瘤",
            "secondary": ["低蛋白血症", "近期体重下降"],
            "risk_note": "进食减少、体重下降明显，存在营养风险；有长期吸烟史",
        },
    },
    {
        "patient_no": "P-DEMO-0003",
        "patient_name": "王秀兰",
        "sex": "女",
        "birthday": "1940-11-02",
        "id_card": "110101194011020038",
        "phone": "13800000003",
        "encounter_no": "E-DEMO-0003",
        "inpatient_no": "ZY0003",
        "department_code": "NEUR",
        "department_name": "神经内科",
        "ward_name": "神经内科病区",
        "bed_no": "05-3",
        "admission_offset_days": 5,
        "diagnosis_snapshot": {
            "primary": "脑卒中后遗症",
            "secondary": ["长期卧床", "大小便失禁"],
            "risk_note": "长期卧床、活动受限，压疮风险高；ADL 明显受限",
        },
    },
    {
        "patient_no": "P-DEMO-0004",
        "patient_name": "陈建军",
        "sex": "男",
        "birthday": "1968-01-18",
        "id_card": "110101196801180043",
        "phone": "13800000004",
        "encounter_no": "E-DEMO-0004",
        "inpatient_no": "ZY0004",
        "department_code": "RESP",
        "department_name": "呼吸与危重症医学科",
        "ward_name": "呼吸内科病区",
        "bed_no": "16-1",
        "admission_offset_days": 1,
        "diagnosis_snapshot": {
            "primary": "慢性阻塞性肺疾病急性加重",
            "secondary": ["II型呼吸衰竭"],
            "risk_note": "长期大量吸烟、每天1包以上，需戒烟宣教；有饮酒习惯",
        },
    },
    {
        "patient_no": "P-DEMO-0005",
        "patient_name": "赵敏",
        "sex": "女",
        "birthday": "1985-09-30",
        "id_card": "110101198509300051",
        "phone": "13800000005",
        "encounter_no": "E-DEMO-0005",
        "inpatient_no": "ZY0005",
        "department_code": "ORTH",
        "department_name": "骨科",
        "ward_name": "骨科病区",
        "bed_no": "22-2",
        "admission_offset_days": 1,
        "diagnosis_snapshot": {
            "primary": "左股骨颈骨折",
            "secondary": ["青霉素过敏史"],
            "risk_note": "术后早期、下肢制动，跌倒/坠床风险；有明确药物过敏史",
        },
    },
]


class PatientSeeder:
    """演示患者幂等种子导入器。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        identity_secret: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._identity_secret = (
            identity_secret
            or get_app_config().security.patient_identity_secret
        )

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    def seed(self) -> dict[str, int]:
        """幂等写入演示患者与在院记录。"""
        now = datetime.now(UTC)
        stats = {
            "patient_created": 0,
            "patient_updated": 0,
            "encounter_created": 0,
            "encounter_updated": 0,
            "total": len(PATIENT_SEEDS),
        }
        with self._new_session() as db:
            try:
                for seed in PATIENT_SEEDS:
                    patient, created = self._upsert_patient(db, seed)
                    stats["patient_created" if created else "patient_updated"] += 1
                    db.flush()
                    encounter_created = self._upsert_encounter(
                        db,
                        seed,
                        patient.id,
                        now,
                    )
                    stats[
                        "encounter_created" if encounter_created else "encounter_updated"
                    ] += 1
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("演示患者种子导入失败")
                raise
        logger.info("演示患者种子导入完成: %s", stats)
        return stats

    def _upsert_patient(self, db: Session, seed: dict) -> tuple[Patient, bool]:
        """按患者编号幂等写入患者主档。"""
        patient = db.scalar(
            select(Patient).where(Patient.patient_no == seed["patient_no"])
        )
        birthday = date.fromisoformat(seed["birthday"])
        encrypted_id_card = encrypt_id_card(
            seed["id_card"],
            self._identity_secret,
        )
        if patient is None:
            patient = Patient(
                patient_no=seed["patient_no"],
                his_patient_id=seed["patient_no"],
                patient_name=seed["patient_name"],
                sex=seed["sex"],
                birthday=birthday,
                phone=seed["phone"],
                id_card_ciphertext=encrypted_id_card,
                creator="seed",
            )
            db.add(patient)
            return patient, True

        patient.his_patient_id = seed["patient_no"]
        patient.patient_name = seed["patient_name"]
        patient.sex = seed["sex"]
        patient.birthday = birthday
        patient.phone = seed["phone"]
        patient.id_card_ciphertext = encrypted_id_card
        patient.updator = "seed"
        return patient, False

    @staticmethod
    def _upsert_encounter(
        db: Session,
        seed: dict,
        patient_id: int,
        now: datetime,
    ) -> bool:
        """按住院过程编号幂等写入在院记录。"""
        encounter = db.scalar(
            select(PatientEncounter).where(
                PatientEncounter.encounter_no == seed["encounter_no"]
            )
        )
        if encounter is None:
            encounter = PatientEncounter(
                encounter_no=seed["encounter_no"],
                patient_id=patient_id,
                inpatient_no=seed["inpatient_no"],
                department_code=seed["department_code"],
                department_name=seed["department_name"],
                ward_name=seed["ward_name"],
                bed_no=seed["bed_no"],
                admission_time=now - timedelta(days=seed["admission_offset_days"]),
                encounter_status="在院",
                diagnosis_snapshot=seed["diagnosis_snapshot"],
                creator="seed",
            )
            db.add(encounter)
            return True

        encounter.patient_id = patient_id
        encounter.inpatient_no = seed["inpatient_no"]
        encounter.department_code = seed["department_code"]
        encounter.department_name = seed["department_name"]
        encounter.ward_name = seed["ward_name"]
        encounter.bed_no = seed["bed_no"]
        encounter.encounter_status = "在院"
        encounter.discharge_time = None
        encounter.diagnosis_snapshot = seed["diagnosis_snapshot"]
        encounter.updator = "seed"
        return False
