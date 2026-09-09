"""主动健康宣教停用后的关键词规则防回归测试。"""

from app.managers.keyword_matcher import MatchResult


def test_trigger_education_rule_never_emits_constraint_prompt():
    result = MatchResult(
        rule_code="KW_EDUCATION",
        rule_name="宣教触发关键词",
        action_type="trigger_education",
        priority=50,
        action_payload={"prompt": "患者有健康宣教需求"},
    )

    assert result.constraint_prompt == ""


def test_old_constraint_prompt_with_education_is_suppressed():
    old_smoking = MatchResult(
        rule_code="KW_SMOKING",
        rule_name="吸烟史关键词",
        action_type="constraint_prompt",
        priority=100,
        action_payload={
            "prompt": "患者提及吸烟相关信息，请追问吸烟量，并做戒烟宣教。"
        },
    )
    old_tool = MatchResult(
        rule_code="KW_OLD_TOOL",
        rule_name="旧宣教工具规则",
        action_type="constraint_prompt",
        priority=100,
        action_payload={
            "prompt": "请调用 get_education_material(category='tobacco')"
        },
    )

    assert old_smoking.constraint_prompt == ""
    assert old_tool.constraint_prompt == ""


def test_non_education_constraint_is_preserved():
    result = MatchResult(
        rule_code="KW_SMOKING",
        rule_name="吸烟史关键词",
        action_type="constraint_prompt",
        priority=100,
        action_payload={
            "prompt": "患者提及吸烟相关信息，请仅按量表需要追问每日吸烟量和烟龄。"
        },
    )

    assert result.constraint_prompt == (
        "患者提及吸烟相关信息，请仅按量表需要追问每日吸烟量和烟龄。"
    )
