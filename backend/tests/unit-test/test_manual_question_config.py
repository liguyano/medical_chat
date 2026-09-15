"""题库人工标记输入边界测试。"""

import pytest
from pydantic import ValidationError

from app.schemas.system_config import AssessmentQuestionConfigDto


@pytest.mark.parametrize("value", ["true", "false", 1, None, [], {}])
def test_manual_flag_rejects_non_boolean(value):
    with pytest.raises(ValidationError):
        AssessmentQuestionConfigDto(
            id=1,
            question_code="Q",
            question_name="题",
            original_text="题",
            patient_text="题",
            question_type="text",
            value_type="string",
            required=True,
            scored=False,
            allow_other=False,
            derived=False,
            sort_no=0,
            validation_rule={"manual_required": value},
        )
