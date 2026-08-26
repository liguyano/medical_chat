"""结构化量表目录导入器
作用：将 docs/structured/assessment-scales 中的真实量表转换为模板域记录。
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from medagent.agents.service_agent.extraction_agent.types import normalize_answer_type

from app.models import (
    AssessmentActionDefinition,
    AssessmentOption,
    AssessmentQuestion,
    AssessmentRule,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSection,
)
from app.models import base as model_base

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "pending_review": "审核中",
    "draft": "草稿",
    "published": "已发布",
    "disabled": "已停用",
}
TYPE_VALUE_MAP = {
    "text": "string",
    "textarea": "string",
    "integer": "number",
    "decimal": "number",
    "boolean": "boolean",
    "date": "date",
    "datetime": "date",
    "single_choice": "string",
    "multiple_choice": "string",
    "grouped_choice": "string",
}
DERIVED_EXPRESSIONS = {
    "sex": "patient.sex",
    "age": "assessment_instance.age_snapshot",
    "bmi": "weight_kg / (height_cm / 100) ** 2",
    "weight_loss_percent": "(previous_weight_kg - current_weight_kg) / previous_weight_kg * 100",
    "age_score": "1 if assessment_instance.age_snapshot > 70 else 0",
    "adl_score": "reference('adl')",
    "fall_score": "reference('fall_risk')",
    "pressure_injury_score": "reference('braden_pressure_injury')",
    "pain_score": "reference('pain_scale')",
    "nutrition_score": "reference('nrs2002')",
    "aspiration_risk_score": "reference('aspiration_risk')",
}


def _normalize_payload_types(value: Any) -> Any:
    """归一化结构化量表快照中的 type/answer_type 字段。"""
    if isinstance(value, list):
        return [_normalize_payload_types(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"type", "answer_type"} and isinstance(item, str):
            try:
                normalized[key] = normalize_answer_type(item)
            except ValueError:
                normalized[key] = item
        else:
            normalized[key] = _normalize_payload_types(item)
    return normalized


class AssessmentCatalogImporter:
    """真实结构化量表的幂等导入器。"""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        """初始化导入器。"""
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        """创建数据库会话。"""
        factory = self._session_factory or model_base.SessionLocal
        if factory is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return factory()

    def import_directory(
        self,
        directory: str | Path,
        *,
        publish_status: str | None = None,
    ) -> dict[str, int]:
        """导入目录中 index.json 声明的全部量表
        Args:
            - directory: 结构化量表目录
            - publish_status: 可选状态覆盖，仅测试或临床审核发布时使用
        Return:
            - 各类新增记录计数
        """
        root = Path(directory)
        index = self._read_json(root / "index.json")
        counters = {
            "scales": 0,
            "versions": 0,
            "sections": 0,
            "questions": 0,
            "options": 0,
            "rules": 0,
            "actions": 0,
            "skipped_versions": 0,
            "promoted_versions": 0,
        }
        with self._new_session() as db:
            try:
                for form in index["forms"]:
                    payload = self._read_json(root / form["structured_file"])
                    self._import_scale(
                        db,
                        payload,
                        schema_version=index["schema_version"],
                        publish_status=publish_status,
                        counters=counters,
                    )
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("结构化量表目录导入失败: %s", root)
                raise
        return counters

    def _import_scale(
        self,
        db: Session,
        payload: dict[str, Any],
        *,
        schema_version: str,
        publish_status: str | None,
        counters: dict[str, int],
    ) -> None:
        """导入一个量表及其完整版本。"""
        payload = _normalize_payload_types(payload)
        content_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        scale = db.scalar(
            select(AssessmentScale).where(
                AssessmentScale.scale_code == payload["id"],
                AssessmentScale.deleted == 0,
            )
        )
        source_status = str(payload.get("status", "draft"))
        desired_status = publish_status or STATUS_MAP.get(source_status, "草稿")
        if scale is None:
            scale = AssessmentScale(
                scale_code=payload["id"],
                scale_name=payload["title"],
                scale_type=payload["form_type"],
                clinical_purpose=None,
                applicable_scope=None,
                source_file=payload.get("source_file"),
                status=desired_status,
                creator="structured_catalog_importer",
            )
            db.add(scale)
            db.flush()
            counters["scales"] += 1
        elif publish_status is not None and scale.status != publish_status:
            scale.status = publish_status
            scale.updator = "structured_catalog_importer"

        existing_version = db.scalar(
            select(AssessmentScaleVersion).where(
                AssessmentScaleVersion.scale_id == scale.id,
                AssessmentScaleVersion.content_hash == content_hash,
                AssessmentScaleVersion.deleted == 0,
            )
        )
        if existing_version is not None:
            if (
                publish_status is not None
                and existing_version.publish_status != publish_status
            ):
                existing_version.publish_status = publish_status
                existing_version.updator = "structured_catalog_importer"
                counters["promoted_versions"] += 1
            counters["skipped_versions"] += 1
            return

        version_code = f"{schema_version}-{content_hash[:12]}"
        version = AssessmentScaleVersion(
            scale_id=scale.id,
            version_code=version_code,
            version_name=f"{payload['title']} {schema_version}",
            publish_status=desired_status,
            effective_time=None,
            expire_time=None,
            scale_snapshot=payload,
            content_hash=content_hash,
            creator="structured_catalog_importer",
        )
        db.add(version)
        db.flush()
        counters["versions"] += 1

        sort_no = 0
        for section_code, section_name, fields in self._iter_sections(payload):
            section = AssessmentSection(
                scale_version_id=version.id,
                parent_section_id=None,
                section_code=section_code,
                section_name=section_name,
                section_description=None,
                display_condition=None,
                sort_no=counters["sections"] + 1,
                creator="structured_catalog_importer",
            )
            db.add(section)
            db.flush()
            counters["sections"] += 1
            for field in fields:
                sort_no += 1
                self._import_question(
                    db,
                    version_id=version.id,
                    section_id=section.id,
                    field=field,
                    sort_no=sort_no,
                    counters=counters,
                )

        self._import_rules(db, version.id, payload, counters)
        self._import_actions(db, version.id, payload, counters)

    def _import_question(
        self,
        db: Session,
        *,
        version_id: int,
        section_id: int,
        field: dict[str, Any],
        sort_no: int,
        counters: dict[str, int],
    ) -> None:
        """导入一个问题及其选项。"""
        source_type = field.get("type") or (
            "single_choice" if field.get("options") else "text"
        )
        try:
            question_type = normalize_answer_type(source_type)
        except ValueError:
            question_type = "text"
        value_type = TYPE_VALUE_MAP.get(question_type, "string")
        derived = field["id"] in DERIVED_EXPRESSIONS
        options = self._normalize_options(field)
        if options and question_type == "text":
            question_type = "single_choice"
            value_type = "string"

        question = AssessmentQuestion(
            scale_version_id=version_id,
            section_id=section_id,
            question_code=field["id"],
            question_name=field["label"],
            original_text=str(field.get("original_text") or field["label"]),
            patient_text=str(
                field.get("patient_text")
                or self._patient_text(field["label"], question_type)
            ),
            nurse_text=str(field.get("nurse_text") or field["label"]),
            question_type=question_type,
            value_type=value_type,
            required=not derived,
            scored=any(option.get("score") is not None for option in options),
            unit=field.get("unit"),
            value_precision=self._parse_precision(field.get("precision")),
            allow_other=any(
                "其他" in str(option.get("label", "")) for option in options
            ),
            derived=derived,
            calculation_expression=DERIVED_EXPRESSIONS.get(field["id"]),
            validation_rule=field.get("validation_rule"),
            sort_no=sort_no,
            creator="structured_catalog_importer",
        )
        db.add(question)
        db.flush()
        counters["questions"] += 1

        for option_sort, option in enumerate(options, 1):
            code = str(option.get("id") or option.get("value") or f"option_{option_sort}")
            score = option.get("score")
            db.add(
                AssessmentOption(
                    question_id=question.id,
                    option_code=code,
                    option_label=str(option["label"]),
                    option_value=str(option.get("value", score if score is not None else code)),
                    clinical_score=score,
                    risk_tag=option.get("risk_tag"),
                    requires_follow_up=bool(
                        option.get("requires_follow_up")
                        or field.get("supporting_fields")
                        or "其他" in str(option["label"])
                    ),
                    extra_input_type=None,
                    extra_input_unit=None,
                    sort_no=option_sort,
                    creator="structured_catalog_importer",
                )
            )
            counters["options"] += 1

    @staticmethod
    def _iter_sections(
        payload: dict[str, Any],
    ) -> list[tuple[str, str, list[dict[str, Any]]]]:
        """将不同量表 JSON 结构归一化为分组和问题。"""
        sections: list[tuple[str, str, list[dict[str, Any]]]] = []
        for section in payload.get("sections", []):
            fields = list(section.get("fields", []))
            fields.extend(
                {
                    "id": group["id"],
                    "label": group["label"],
                    "type": "multiple_choice",
                    "options": group.get("options", []),
                }
                for group in section.get("field_groups", [])
            )
            sections.append((section["id"], section["title"], fields))

        if payload.get("measurement_fields"):
            sections.append(("measurements", "测量指标", payload["measurement_fields"]))
        if payload.get("initial_screening", {}).get("items"):
            sections.append(
                ("initial_screening", "初筛", payload["initial_screening"]["items"])
            )
        scoring = payload.get("scoring", {})
        scoring_fields = list(scoring.get("items", []))
        scoring_fields.extend(scoring.get("components", []))
        scoring_fields.extend(
            supporting_field
            for field in list(scoring_fields)
            for supporting_field in field.get("supporting_fields", [])
        )
        if scoring_fields:
            sections.append(("scoring", "量表评分", scoring_fields))
        return sections

    @staticmethod
    def _normalize_options(field: dict[str, Any]) -> list[dict[str, Any]]:
        """统一字符串选项和对象选项。"""
        options: list[dict[str, Any]] = []
        for index, option in enumerate(field.get("options", []), 1):
            if isinstance(option, str):
                options.append({"id": f"option_{index}", "label": option})
            else:
                options.append(dict(option))
        for group_index, group in enumerate(field.get("groups", []), 1):
            for option_index, option in enumerate(group.get("options", []), 1):
                options.append(
                    {
                        "id": f"group_{group_index}_option_{option_index}",
                        "label": f"{group['label']}：{option}",
                    }
                )
        return options

    @staticmethod
    def _import_rules(
        db: Session,
        version_id: int,
        payload: dict[str, Any],
        counters: dict[str, int],
    ) -> None:
        """导入具有明确表达式的结果解释规则。"""
        for index, item in enumerate(payload.get("interpretation", []), 1):
            db.add(
                AssessmentRule(
                    scale_version_id=version_id,
                    rule_code=f"interpretation_{index}",
                    rule_type="结果解释",
                    condition_expression={"expression": item["condition"]},
                    result_payload={"result": item["result"]},
                    priority=index,
                    status="启用",
                    creator="structured_catalog_importer",
                )
            )
            counters["rules"] += 1

    @staticmethod
    def _import_actions(
        db: Session,
        version_id: int,
        payload: dict[str, Any],
        counters: dict[str, int],
    ) -> None:
        """导入量表定义的护理措施。"""
        for index, name in enumerate(payload.get("nursing_measures", []), 1):
            db.add(
                AssessmentActionDefinition(
                    scale_version_id=version_id,
                    action_code=f"nursing_measure_{index}",
                    action_group="护理措施",
                    action_name=name,
                    action_type="护理措施",
                    input_type="勾选",
                    allow_other=False,
                    trigger_rule_id=None,
                    sort_no=index,
                    creator="structured_catalog_importer",
                )
            )
            counters["actions"] += 1

    @staticmethod
    def _patient_text(label: str, question_type: str) -> str:
        """生成保守、可追溯的患者口语化问题。"""
        if label.endswith(("？", "?")):
            return label
        try:
            question_type = normalize_answer_type(question_type)
        except ValueError:
            pass
        if question_type == "boolean":
            return f"请问“{label}”这一项是否符合您的情况？"
        return f"请问您的“{label}”情况是怎样的？"

    @staticmethod
    def _parse_precision(value: Any) -> int | None:
        """从 0.1cm 等文本中提取小数位数。"""
        if not isinstance(value, str) or "." not in value:
            return None
        decimal = value.split(".", 1)[1]
        digits = "".join(character for character in decimal if character.isdigit())
        return len(digits) if digits else None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        """读取 UTF-8 JSON 文件。"""
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            raise TypeError(f"量表 JSON 顶层必须是对象: {path}")
        return payload
