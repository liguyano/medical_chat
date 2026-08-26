"""结构化量表目录和归一化逻辑单元测试。"""

import json
from pathlib import Path

from app.managers.assessment_catalog_importer import AssessmentCatalogImporter


CATALOG_DIR = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "structured"
    / "assessment-scales"
)


def test_catalog_index_contains_all_dialogue_scales():
    """目录应包含原有五张和新增十一张量表，且每个文件可解析。"""
    index = json.loads((CATALOG_DIR / "index.json").read_text(encoding="utf-8"))
    assert len(index["forms"]) == 16
    assert len({form["id"] for form in index["forms"]}) == 16
    total_questions = 0
    total_options = 0
    for form in index["forms"]:
        payload = json.loads(
            (CATALOG_DIR / form["structured_file"]).read_text(encoding="utf-8")
        )
        assert payload["id"] == form["id"]
        assert payload["status"] == "pending_review"
        sections = AssessmentCatalogImporter._iter_sections(payload)
        fields = [field for _, _, section_fields in sections for field in section_fields]
        total_questions += len(fields)
        total_options += sum(
            len(AssessmentCatalogImporter._normalize_options(field))
            for field in fields
        )

    assert total_questions >= 140
    assert total_options > 280


def test_new_scale_key_scores_and_rules_are_preserved():
    """新增量表的关键计分和判定边界应与结构化来源一致。"""
    frail = json.loads((CATALOG_DIR / "frail.json").read_text(encoding="utf-8"))
    assert len(frail["scoring"]["items"]) == 5
    assert frail["interpretation"][0] == {
        "condition": "total_score >= 3",
        "result": "衰弱",
    }

    pain = json.loads(
        (CATALOG_DIR / "chronic-pain-nrs.json").read_text(encoding="utf-8")
    )
    pain_scores = [
        option["score"] for option in pain["scoring"]["items"][0]["options"]
    ]
    assert pain_scores == list(range(11))

    mna = json.loads((CATALOG_DIR / "mna-sf.json").read_text(encoding="utf-8"))
    assert mna["scoring"]["score_range"] == {"min": 0, "max": 14}
    assert mna["interpretation"][0]["condition"] == "total_score <= 11"


def test_iter_sections_supports_all_catalog_shapes():
    """分组、测量、初筛、评分项和组件都应归一化。"""
    payload = {
        "sections": [
            {
                "id": "base",
                "title": "基础",
                "fields": [{"id": "age", "label": "年龄", "type": "integer"}],
                "field_groups": [
                    {"id": "focus", "label": "重点", "options": ["A", "B"]}
                ],
            }
        ],
        "measurement_fields": [{"id": "weight", "label": "体重", "type": "decimal"}],
        "initial_screening": {
            "items": [{"id": "screen", "label": "初筛", "type": "boolean"}]
        },
        "scoring": {
            "items": [{"id": "item", "label": "评分", "options": ["A"]}],
            "components": [
                {
                    "id": "component",
                    "label": "组件",
                    "options": ["B"],
                    "supporting_fields": [
                        {"id": "support", "label": "补充", "type": "text"}
                    ],
                }
            ],
        },
    }
    sections = AssessmentCatalogImporter._iter_sections(payload)
    codes = [field["id"] for _, _, fields in sections for field in fields]
    assert codes == [
        "age",
        "focus",
        "weight",
        "screen",
        "item",
        "component",
        "support",
    ]


def test_normalize_options_supports_strings_objects_and_groups():
    """三类选项结构应归一化为对象列表。"""
    options = AssessmentCatalogImporter._normalize_options(
        {
            "options": ["文本选项", {"score": 2, "label": "计分选项"}],
            "groups": [{"label": "呼之", "options": ["能应"]}],
        }
    )
    assert [option["label"] for option in options] == [
        "文本选项",
        "计分选项",
        "呼之：能应",
    ]
    assert options[1]["score"] == 2


def test_patient_text_is_conservative_and_traceable():
    """自动口语化不得改变临床字段含义。"""
    assert (
        AssessmentCatalogImporter._patient_text("是否卧床", "布尔")
        == "请问“是否卧床”这一项是否符合您的情况？"
    )
    assert (
        AssessmentCatalogImporter._patient_text("您是否吸烟？", "单选")
        == "您是否吸烟？"
    )


def test_precision_parser():
    """精度文本应转换为数据库小数位数。"""
    assert AssessmentCatalogImporter._parse_precision("0.1cm") == 1
    assert AssessmentCatalogImporter._parse_precision(None) is None


def test_import_question_preserves_explicit_patient_text_and_validation_rule():
    """结构化量表声明的患者问法和校验规则应进入数据库字段。"""
    class FakeSession:
        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)

        def flush(self):
            pass

    field = {
        "id": "pain",
        "label": "当前疼痛",
        "type": "integer",
        "patient_text": "请按0到10分评价您现在的疼痛程度。",
        "validation_rule": {"min": 0, "max": 10},
    }
    session = FakeSession()
    AssessmentCatalogImporter()._import_question(
        session,
        version_id=1,
        section_id=1,
        field=field,
        sort_no=1,
        counters={"questions": 0, "options": 0},
    )
    question = session.added[0]
    assert question.patient_text == field["patient_text"]
    assert question.validation_rule == field["validation_rule"]
