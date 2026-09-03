"""患者对话题目进度响应。"""

from typing import Literal

from pydantic import BaseModel


class DialogQuestionItem(BaseModel):
    question_id: int
    question_code: str
    question_text: str
    scale_name: str
    required: bool
    status: Literal["unasked", "asked", "recorded"]
    is_current: bool
    cooling_until_turn: int | None


class DialogQuestionProgress(BaseModel):
    session_id: str
    current: int
    total: int
    turn_number: int
    active_question_id: int | None
    candidate_question_ids: list[int]
    questions: list[DialogQuestionItem]
