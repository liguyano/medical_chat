"""演示患者种子导入器
作用：幂等写入 10 位在院患者及其住院记录，覆盖差异化临床画像，
      供第一期文本对话闭环体验（选患者→勾量表→发任务）使用。
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.configs.app_config import get_app_config
from app.models import base as model_base
from app.models.patient_task import Patient, PatientEncounter
from app.utils.patient_identity import encrypt_id_card, verify_id_card

logger = logging.getLogger(__name__)

# 差异化患者画像种子：覆盖跌倒/营养不良/吸烟史/压疮风险/ADL 受限等场景，
# 便于体验不同量表与关键词拦截。admission_offset_days 为相对今天的入院天数。
_PATIENT_SEEDS: list[dict] = [
    {
        "patient_no": "P-DEMO-0001",
        "patient_name": "张桂芳",
        "id_card_no": "110101194803120010",
        "sex": "女",
        "birthday": "1948-03-12",
        "phone": "13800000001",
        "encounter_no": "E-DEMO-0001",
        "inpatient_no": "ZY0001",
        "department_code": "GERI",
        "department_name": "老年医学科",
        "ward_name": "老年科一病区",
        "bed_no": "12-1",
        "admission_offset_days": 2,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "高血压3级（很高危）",
            "secondary": ["陈旧性脑梗死", "骨质疏松"],
            "risk_note": "高龄、步态不稳、既往跌倒史，跌倒风险高",
        },
    },
    {
        "patient_no": "P-DEMO-0002",
        "patient_name": "李国强",
        "id_card_no": "110101195507250026",
        "sex": "男",
        "birthday": "1955-07-25",
        "phone": "13800000002",
        "encounter_no": "E-DEMO-0002",
        "inpatient_no": "ZY0002",
        "department_code": "GAST",
        "department_name": "消化内科",
        "ward_name": "消化内科病区",
        "bed_no": "08-2",
        "admission_offset_days": 3,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "胃恶性肿瘤",
            "secondary": ["低蛋白血症", "近期体重下降"],
            "risk_note": "进食减少、体重下降明显，存在营养风险；有长期吸烟史",
        },
    },
    {
        "patient_no": "P-DEMO-0003",
        "patient_name": "王秀兰",
        "id_card_no": "110101194011020038",
        "sex": "女",
        "birthday": "1940-11-02",
        "phone": "13800000003",
        "encounter_no": "E-DEMO-0003",
        "inpatient_no": "ZY0003",
        "department_code": "NEUR",
        "department_name": "神经内科",
        "ward_name": "神经内科病区",
        "bed_no": "05-3",
        "admission_offset_days": 5,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "脑卒中后遗症",
            "secondary": ["长期卧床", "大小便失禁"],
            "risk_note": "长期卧床、活动受限，压疮风险高；ADL 明显受限",
        },
    },
    {
        "patient_no": "P-DEMO-0004",
        "patient_name": "陈建军",
        "id_card_no": "110101196801180043",
        "sex": "男",
        "birthday": "1968-01-18",
        "phone": "13800000004",
        "encounter_no": "E-DEMO-0004",
        "inpatient_no": "ZY0004",
        "department_code": "RESP",
        "department_name": "呼吸与危重症医学科",
        "ward_name": "呼吸内科病区",
        "bed_no": "16-1",
        "admission_offset_days": 1,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "慢性阻塞性肺疾病急性加重",
            "secondary": ["II型呼吸衰竭"],
            "risk_note": "长期大量吸烟、每天1包以上，需戒烟宣教；有饮酒习惯",
        },
    },
    {
        "patient_no": "P-DEMO-0005",
        "patient_name": "赵敏",
        "id_card_no": "110101198509300051",
        "sex": "女",
        "birthday": "1985-09-30",
        "phone": "13800000005",
        "encounter_no": "E-DEMO-0005",
        "inpatient_no": "ZY0005",
        "department_code": "ORTH",
        "department_name": "骨科",
        "ward_name": "骨科病区",
        "bed_no": "22-2",
        "admission_offset_days": 1,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "左股骨颈骨折",
            "secondary": ["青霉素过敏史"],
            "risk_note": "术后早期、下肢制动，跌倒/坠床风险；有明确药物过敏史",
        },
    },
    {
        "patient_no": "P-DEMO-0006",
        "patient_name": "周海燕",
        "id_card_no": "110101197206150028",
        "sex": "女",
        "birthday": "1972-06-15",
        "phone": "13800000006",
        "encounter_no": "E-DEMO-0006",
        "inpatient_no": "ZY0006",
        "department_code": "ENDO",
        "department_name": "内分泌科",
        "ward_name": "内分泌科病区",
        "bed_no": "09-1",
        "admission_offset_days": 2,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "2型糖尿病",
            "secondary": ["糖尿病周围神经病变"],
            "risk_note": "血糖控制不稳定，需要低血糖风险与足部护理评估",
        },
    },
    {
        "patient_no": "P-DEMO-0007",
        "patient_name": "孙志伟",
        "id_card_no": "110101196212080035",
        "sex": "男",
        "birthday": "1962-12-08",
        "phone": "13800000007",
        "encounter_no": "E-DEMO-0007",
        "inpatient_no": "ZY0007",
        "department_code": "CARD",
        "department_name": "心血管内科",
        "ward_name": "心血管内科病区",
        "bed_no": "18-2",
        "admission_offset_days": 4,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "冠状动脉粥样硬化性心脏病",
            "secondary": ["高脂血症"],
            "risk_note": "活动耐量下降，需关注胸痛、用药依从性和跌倒风险",
        },
    },
    {
        "patient_no": "P-DEMO-0008",
        "patient_name": "杨秀梅",
        "id_card_no": "110101197904220026",
        "sex": "女",
        "birthday": "1979-04-22",
        "phone": "13800000008",
        "encounter_no": "E-DEMO-0008",
        "inpatient_no": "ZY0008",
        "department_code": "ONCO",
        "department_name": "肿瘤科",
        "ward_name": "肿瘤科病区",
        "bed_no": "06-1",
        "admission_offset_days": 3,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "乳腺恶性肿瘤",
            "secondary": ["化疗后乏力"],
            "risk_note": "近期接受化疗，存在营养风险和感染风险",
        },
    },
    {
        "patient_no": "P-DEMO-0009",
        "patient_name": "黄建国",
        "id_card_no": "110101195010090019",
        "sex": "男",
        "birthday": "1950-10-09",
        "phone": "13800000009",
        "encounter_no": "E-DEMO-0009",
        "inpatient_no": "ZY0009",
        "department_code": "URO",
        "department_name": "泌尿外科",
        "ward_name": "泌尿外科病区",
        "bed_no": "11-2",
        "admission_offset_days": 1,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "前列腺增生",
            "secondary": ["尿潴留"],
            "risk_note": "留置导尿，需进行管路安全、感染预防和活动能力评估",
        },
    },
    {
        "patient_no": "P-DEMO-0010",
        "patient_name": "林晓莉",
        "id_card_no": "11010119920214002X",
        "sex": "女",
        "birthday": "1992-02-14",
        "phone": "13800000010",
        "encounter_no": "E-DEMO-0010",
        "inpatient_no": "ZY0010",
        "department_code": "OBGYN",
        "department_name": "妇产科",
        "ward_name": "妇科病区",
        "bed_no": "03-2",
        "admission_offset_days": 1,
        "encounter_status": "在院",
        "diagnosis_snapshot": {
            "primary": "子宫肌瘤",
            "secondary": ["术前焦虑"],
            "risk_note": "计划手术，需关注知情同意理解和术前焦虑程度",
        },
    },
]


class PatientSeeder:
    """演示患者幂等种子导入器
    作用：按 patient_no / encounter_no 幂等 upsert 患者与住院记录。
    类参数：
        - session_factory: 可选会话工厂；为空时使用全局 SessionLocal
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
        identity_secret: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._identity_secret = identity_secret

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    def seed(self) -> dict[str, int]:
        """幂等写入演示患者与住院记录
        作用：存在则更新画像字段，不存在则新建；保证多次执行结果一致。
        Return:
            - 统计字典 {patient_created, patient_updated, encounter_created, encounter_updated, total}
        """
        now = datetime.now(UTC)
        identity_secret = (
            self._identity_secret or get_app_config().security.patient_identity_secret
        )
        stats = {
            "patient_created": 0,
            "patient_updated": 0,
            "encounter_created": 0,
            "encounter_updated": 0,
            "total": len(_PATIENT_SEEDS),
        }

        with self._new_session() as db:
            try:
                for seed in _PATIENT_SEEDS:
                    patient, created = self._upsert_patient(db, seed, identity_secret)
                    stats["patient_created" if created else "patient_updated"] += 1
                    # 需要 patient.id 才能建住院记录，先 flush 拿主键
                    db.flush()
                    created_enc = self._upsert_encounter(db, seed, patient.id, now)
                    stats["encounter_created" if created_enc else "encounter_updated"] += 1
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("演示患者种子导入失败")
                raise

        logger.info("演示患者种子导入完成: %s", stats)
        return stats

    @staticmethod
    def _upsert_patient(
        db: Session,
        seed: dict,
        identity_secret: str,
    ) -> tuple[Patient, bool]:
        """按 patient_no 幂等写入患者主档
        Return:
            - (patient, created)：created 为 True 表示新建
        """
        existing = db.scalar(
            select(Patient).where(Patient.patient_no == seed["patient_no"])
        )
        birthday = date.fromisoformat(seed["birthday"])
        if existing is None:
            patient = Patient(
                patient_no=seed["patient_no"],
                patient_name=seed["patient_name"],
                sex=seed["sex"],
                birthday=birthday,
                phone=seed["phone"],
                id_card_ciphertext=encrypt_id_card(
                    seed["id_card_no"],
                    identity_secret,
                ),
                creator="seed",
            )
            db.add(patient)
            return patient, True

        # 更新画像字段（保持幂等）
        existing.patient_name = seed["patient_name"]
        existing.sex = seed["sex"]
        existing.birthday = birthday
        existing.phone = seed["phone"]
        existing.deleted = 0
        if not verify_id_card(
            seed["id_card_no"],
            existing.id_card_ciphertext,
            identity_secret,
        ):
            existing.id_card_ciphertext = encrypt_id_card(
                seed["id_card_no"],
                identity_secret,
            )
        existing.updator = "seed"
        return existing, False

    @staticmethod
    def _upsert_encounter(
        db: Session,
        seed: dict,
        patient_id: int,
        now: datetime,
    ) -> bool:
        """按 encounter_no 幂等写入住院记录
        Return:
            - bool: True 表示新建，False 表示更新
        """
        admission_time = now - timedelta(days=seed["admission_offset_days"])
        existing = db.scalar(
            select(PatientEncounter).where(
                PatientEncounter.encounter_no == seed["encounter_no"]
            )
        )
        if existing is None:
            db.add(
                PatientEncounter(
                    encounter_no=seed["encounter_no"],
                    patient_id=patient_id,
                    inpatient_no=seed["inpatient_no"],
                    department_code=seed["department_code"],
                    department_name=seed["department_name"],
                    ward_name=seed["ward_name"],
                    bed_no=seed["bed_no"],
                    admission_time=admission_time,
                    encounter_status=seed["encounter_status"],
                    diagnosis_snapshot=seed["diagnosis_snapshot"],
                    creator="seed",
                )
            )
            return True

        # 更新住院画像（保持在院状态，入院时间保持相对稳定）
        existing.patient_id = patient_id
        existing.inpatient_no = seed["inpatient_no"]
        existing.department_code = seed["department_code"]
        existing.department_name = seed["department_name"]
        existing.ward_name = seed["ward_name"]
        existing.bed_no = seed["bed_no"]
        existing.encounter_status = seed["encounter_status"]
        existing.diagnosis_snapshot = seed["diagnosis_snapshot"]
        existing.deleted = 0
        existing.updator = "seed"
        return False
