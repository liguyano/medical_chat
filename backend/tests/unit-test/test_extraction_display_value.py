"""结构化答案用户可见值测试。"""

from decimal import Decimal

from app.services.extraction_service import _build_display_value


def test_option_labels_are_used_instead_of_codes():
    """选项答案应展示量表标签，而不是 option_3 等内部编码。"""
    assert (
        _build_display_value(
            answer_text=None,
            answer_number=Decimal(3),
            answer_boolean=None,
            selected_labels=["10年以上"],
        )
        == "10年以上"
    )


def test_scalar_answers_keep_original_value():
    """文本、数值和布尔答案保持真实值。"""
    assert (
        _build_display_value(
            answer_text="胸闷",
            answer_number=None,
            answer_boolean=None,
            selected_labels=None,
        )
        == "胸闷"
    )
    assert (
        _build_display_value(
            answer_text=None,
            answer_number=Decimal(10),
            answer_boolean=None,
            selected_labels=None,
        )
        == "10"
    )
    assert (
        _build_display_value(
            answer_text=None,
            answer_number=None,
            answer_boolean=False,
            selected_labels=None,
        )
        == "否"
    )
