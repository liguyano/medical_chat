"""护士 AI 质量评价接口单元测试。"""

import pytest
from pydantic import ValidationError

from app.schemas.quality import MessageRatingRequest, QualityReviewRequest
from app.services.quality_review_service import _rating_from_score


def test_message_rating_accepts_score_without_legacy_rating():
    """新 UI 只提交 1～5 分时，后端应自动兼容为 like/dislike。"""
    request = MessageRatingRequest(
        task_id="TASK-1",
        message_id="MSG-1",
        reviewer_id=1,
        score=5,
    )
    assert request.rating is None
    assert _rating_from_score(request.score, request.rating) == "like"


def test_message_rating_requires_rating_or_score():
    """逐条质评不能提交空评价。"""
    with pytest.raises(ValidationError):
        MessageRatingRequest(
            task_id="TASK-1",
            message_id="MSG-1",
            reviewer_id=1,
        )


def test_message_rating_rejects_score_outside_one_to_five():
    """逐条质评分值必须限制在 1～5。"""
    with pytest.raises(ValidationError):
        MessageRatingRequest(
            task_id="TASK-1",
            message_id="MSG-1",
            reviewer_id=1,
            score=6,
        )


def test_quality_review_requires_one_score_group():
    """整体质评至少需要提交一组维度分数。"""
    with pytest.raises(ValidationError):
        QualityReviewRequest(task_id="TASK-1", reviewer_id=1)


def test_quality_review_accepts_dimension_comments_and_evidence():
    """整体质评可以同时保存维度意见和对话证据消息。"""
    request = QualityReviewRequest(
        task_id="TASK-1",
        reviewer_id=1,
        dialogue_scores={"追问合理性": 4},
        dialogue_comments={"追问合理性": "抓住了异常答案继续追问"},
        evidence_message_ids={"追问合理性": ["MSG-1"]},
    )
    assert request.dialogue_comments["追问合理性"]
    assert request.evidence_message_ids["追问合理性"] == ["MSG-1"]
