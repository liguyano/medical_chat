"""Extraction Agent 有效答案边界测试。"""

from types import SimpleNamespace
from unittest.mock import Mock

from app.models import base as model_base
from app.workers.extraction_agent_runner import ExtractionAgentRunner


def _answer(value=None, options=None):
    return SimpleNamespace(
        answer_value=value,
        selected_option_codes=options or [],
    )


def test_empty_extraction_is_not_persistable():
    """None、空字符串和纯空白不得创建结构化答案。"""
    assert ExtractionAgentRunner._has_extracted_value(_answer()) is False
    assert ExtractionAgentRunner._has_extracted_value(_answer("")) is False
    assert ExtractionAgentRunner._has_extracted_value(_answer("   ")) is False


def test_false_zero_and_selected_option_are_persistable():
    """布尔 False、数值 0 和有效选项都是合法答案。"""
    assert ExtractionAgentRunner._has_extracted_value(_answer(False)) is True
    assert ExtractionAgentRunner._has_extracted_value(_answer(0)) is True
    assert (
        ExtractionAgentRunner._has_extracted_value(
            _answer(None, ["smoking_no"])
        )
        is True
    )


def test_current_question_id_prefers_patient_then_asked_message():
    """当前题目优先取患者关联，缺失时回退到同轮 AI 问句关联。"""
    patient = SimpleNamespace(related_question_id=104)
    asked = SimpleNamespace(related_question_id=105)
    assert ExtractionAgentRunner._resolve_current_question_id(patient, asked) == 104

    patient.related_question_id = None
    assert ExtractionAgentRunner._resolve_current_question_id(patient, asked) == 105
    assert ExtractionAgentRunner._resolve_current_question_id(patient, None) is None


def test_unique_extracted_question_backfills_voice_message_association(monkeypatch):
    """一轮唯一有效题目应回填原先无关联的语音问答消息。"""
    patient = SimpleNamespace(message_no="MSG-PATIENT", related_question_id=None)
    assistant = SimpleNamespace(message_no="MSG-AI", related_question_id=None)
    db = SimpleNamespace(
        scalars=Mock(
            return_value=SimpleNamespace(all=lambda: [patient, assistant])
        ),
        commit=Mock(),
    )

    class SessionContext:
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(model_base, "SessionLocal", SessionContext)

    ExtractionAgentRunner._backfill_question_association(
        interaction_session_id=7,
        message_numbers=["MSG-PATIENT", "MSG-AI"],
        question_ids={104},
    )

    assert patient.related_question_id == 104
    assert assistant.related_question_id == 104
    db.commit.assert_called_once_with()


def test_multiple_extracted_questions_do_not_force_message_association(monkeypatch):
    """一轮抽到多个题目时无法代表单一当前题目，不得回填。"""
    session_factory = Mock()
    monkeypatch.setattr(model_base, "SessionLocal", session_factory)

    ExtractionAgentRunner._backfill_question_association(
        interaction_session_id=7,
        message_numbers=["MSG-PATIENT", "MSG-AI"],
        question_ids={104, 105},
    )

    session_factory.assert_not_called()
