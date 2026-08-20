"""Demo 系统配置服务单元测试。"""

from types import SimpleNamespace

import pytest

from app.errors.handlers import AppError
from app.managers.keyword_matcher import KeywordMatcher
from app.services import system_config_service


def test_content_hash_is_stable_for_different_key_order():
    """配置对象键顺序不应改变内容哈希。"""
    assert system_config_service._content_hash({"a": 1, "b": 2}) == (
        system_config_service._content_hash({"b": 2, "a": 1})
    )


def test_invalid_interaction_rule_pattern_is_rejected():
    """无效正则必须在保存前被拒绝。"""
    with pytest.raises(AppError, match="正则表达式无效"):
        system_config_service._validate_patterns(["(未闭合"])


def test_interaction_rule_dto_flattens_json_fields():
    """规则 JSON 应转换为前端可直接编辑的关键词、提示词和标签。"""
    row = SimpleNamespace(
        id=1,
        rule_code="KW_SMOKING",
        rule_name="吸烟史关键词",
        scope_type="global",
        scope_id=None,
        trigger_condition={
            "keywords": ["抽烟", "吸烟"],
            "patterns": ["每天\\d+支"],
        },
        action_type="constraint_prompt",
        action_payload={"prompt": "继续追问", "tags": ["吸烟史"]},
        priority=100,
        status="active",
    )

    result = system_config_service._rule_dto(row)

    assert result.keywords == ["抽烟", "吸烟"]
    assert result.patterns == ["每天\\d+支"]
    assert result.prompt == "继续追问"
    assert result.enabled is True


def test_education_dto_maps_demo_priority_and_switches():
    """宣教数据库结构应映射为配置中心扁平结构。"""
    program = SimpleNamespace(
        id=1,
        program_code="tobacco",
        status="active",
    )
    version = SimpleNamespace(
        id=2,
        version_code="1.0",
        publish_status="published",
        content_snapshot={
            "source_name": "戒烟宣教",
            "requires_acknowledgement": True,
            "auto_play": False,
        },
    )
    unit = SimpleNamespace(
        id=3,
        unit_title="住院戒烟宣教",
        original_text="原文",
        patient_text="通俗文本",
        voice_text="播报文本",
        risk_level="high_risk",
        mandatory=1,
    )

    result = system_config_service._education_dto(program, version, unit)

    assert result.category == "tobacco"
    assert result.priority == "high"
    assert result.auto_play is False
    assert result.enabled is True


def test_keyword_match_refreshes_database_rules_for_each_message(monkeypatch):
    """每条患者消息都应刷新数据库规则，避免其他进程继续使用旧配置。"""
    matcher = KeywordMatcher()
    calls: list[bool] = []

    def fake_load_rules(force: bool = False):
        calls.append(force)
        return []

    monkeypatch.setattr(matcher, "load_rules", fake_load_rules)

    assert matcher.match("患者表达") == []
    assert calls == [True]
