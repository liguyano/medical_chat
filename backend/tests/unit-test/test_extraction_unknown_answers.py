"""患者明确表示不知道/不清楚时的抽取回归测试。"""

from medagent.agents.service_agent.extraction_agent.agent import FieldExtractionAgent
from medagent.agents.service_agent.extraction_agent.prompt import build_system_prompt
from medagent.agents.service_agent.extraction_agent.validator import RawExtractionResult


def _build_unknown(answer_type: str, value: str = "不知道"):
    raw = RawExtractionResult.model_validate(
        {
            "answers": [
                {
                    "question_id": 23,
                    "value": value,
                    "evidence": value,
                    "confidence": 0.95,
                }
            ]
        }
    )
    return FieldExtractionAgent._build_result(
        raw,
        questions=[
            {
                "question_id": 23,
                "question_code": "unknown_demo",
                "answer_type": answer_type,
                "options": [
                    {"option_code": "yes", "option_label": "是", "option_value": "true"},
                    {"option_code": "no", "option_label": "否", "option_value": "false"},
                ],
            }
        ],
        source_message_ids=["MSG-23"],
    )


def test_explicit_unknown_is_recorded_as_text_for_typed_questions():
    """数值/布尔/选择/日期题都允许患者明确回答“不知道”。"""
    for answer_type in ("number", "boolean", "single_choice", "date"):
        result = _build_unknown(answer_type)
        assert result.invalid_answers == []
        assert len(result.extracted_answers) == 1
        answer = result.extracted_answers[0]
        assert answer.answer_type == "text"
        assert answer.answer_value == "不知道"
        assert answer.extraction_confidence == 0.95
        assert result.missing_questions == []


def test_common_unknown_phrases_are_canonicalized():
    """常见的记不清/不确定表达统一保存成患者明确未知。"""
    for phrase in ("不清楚", "记不清了", "不记得", "忘了", "说不准", "不确定"):
        answer = _build_unknown("number", phrase).extracted_answers[0]
        assert answer.answer_type == "text"
        assert answer.answer_value == phrase


def test_extraction_prompt_treats_explicit_unknown_as_valid_answer():
    prompt = build_system_prompt(
        {"scale_name": "测试量表", "version_code": "v1"},
        [
            {
                "question_id": 23,
                "question_code": "weight_loss_percent",
                "question_text": "过去三个月体重下降百分比是多少？",
                "answer_type": "number",
                "options": [],
                "required": True,
            }
        ],
    )
    assert "不知道" in prompt
    assert "不清楚" in prompt
    assert "有效答案" in prompt
    assert "不要继续逼问" in prompt
