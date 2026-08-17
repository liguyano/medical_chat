"""结构化量表归一化逻辑单元测试。"""

from app.managers.assessment_catalog_importer import AssessmentCatalogImporter


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
