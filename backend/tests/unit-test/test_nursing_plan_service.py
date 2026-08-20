"""患者画像与护理计划服务单元测试。"""

import pytest
from pydantic import ValidationError

from app.schemas.nursing_plan import AiNursingPlanOutput
from app.services.nursing_plan_service import (
    _parse_model_output,
    generate_ai_output,
)

VALID_OUTPUT = {
    "profile": {
        "cooperation_level": "partial",
        "cognition_level": "clear",
        "self_care_level": "partial_assistance",
        "fall_risk_level": "medium",
        "pressure_risk_level": "low",
        "nutrition_risk_level": "medium",
        "communication_level": "good",
        "education_need_level": "high",
        "summary": "患者可正常交流，需要重点确认宣教理解情况。",
        "evidence": ["跌倒量表中风险项", "患者对话反馈"],
    },
    "risk_summary": "存在中等跌倒和营养风险。",
    "education_summary": "采用短句宣教并请患者复述。",
    "handover_summary": "交接班关注首次下床和进食情况。",
    "items": [
        {
            "item_type": "observation",
            "item_code": "fall_observation",
            "item_content": "首次下床时陪同并观察步态。",
            "source_type": "assessment_score",
            "source_id": "score-1",
            "priority": "high",
        }
    ],
}


class FakeChatModel:
    """只实现护理计划服务需要的异步模型最小协议。"""

    async def ainvoke(self, _messages):
        class Response:
            content = f"```json\n{VALID_OUTPUT}\n```".replace("'", '"')

        return Response()


def test_parse_model_output_accepts_json_code_fence():
    """模型偶尔返回代码围栏时仍应提取结构化 JSON。"""
    parsed = _parse_model_output(
        '```json\n{"profile": {"cooperation_level": "good", '
        '"cognition_level": "clear", "self_care_level": "independent", '
        '"fall_risk_level": "low", "pressure_risk_level": "low", '
        '"nutrition_risk_level": "low", "communication_level": "good", '
        '"education_need_level": "low", "summary": "ok"}, '
        '"risk_summary": "none", "education_summary": "none", '
        '"handover_summary": "none", "items": [{"item_type": "education", '
        '"item_code": "e1", "item_content": "说明", '
        '"source_type": "dialogue_summary", "priority": "low"}]}\n```'
    )
    assert parsed.profile.cooperation_level == "good"
    assert parsed.items[0].item_code == "e1"


@pytest.mark.asyncio
async def test_generate_ai_output_validates_model_json():
    """注入模型替身时应返回 Pydantic 校验后的输出。"""
    output, model_name = await generate_ai_output(
        {"task": {"task_id": 1}, "assessments": []},
        model=FakeChatModel(),  # type: ignore[arg-type]
    )
    assert isinstance(output, AiNursingPlanOutput)
    assert output.profile.education_need_level == "high"
    assert model_name == "injected-test-model"


def test_invalid_output_is_rejected():
    """缺少护理明细时不能静默保存无效 AI 结果。"""
    invalid = dict(VALID_OUTPUT)
    invalid["items"] = []
    with pytest.raises(ValidationError):
        _parse_model_output(str(invalid))
