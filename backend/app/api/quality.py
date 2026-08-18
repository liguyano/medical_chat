"""护士 AI 质量评价路由。
作用：提供逐条消息质评和整次 AI 质量评价的新增、更新与查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.quality import (
    MessageRatingListResponse,
    MessageRatingRequest,
    MessageRatingResponse,
    QualityReviewRequest,
    QualityReviewResponse,
)
from app.schemas.response import ApiResponse, ok
from app.services import quality_review_service

router = APIRouter(tags=["quality"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/api/rating",
    response_model=ApiResponse[MessageRatingResponse],
    summary="提交单条 AI 消息质评",
)
def submit_message_rating(
    req: MessageRatingRequest,
    db: DbSession,
) -> dict:
    """保存或更新护士对单条 AI 消息的 1～5 分、点赞/点踩和备注。"""
    return ok(quality_review_service.submit_message_rating(db, req))


@router.get(
    "/api/rating",
    response_model=ApiResponse[MessageRatingListResponse],
    summary="查询任务逐条 AI 消息质评",
)
def list_message_ratings(
    task_id: str,
    db: DbSession,
    reviewer_id: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """读取指定护士在任务下的全部逐条质评。"""
    return ok(quality_review_service.list_message_ratings(db, task_id, reviewer_id))


@router.post(
    "/api/quality-reviews",
    response_model=ApiResponse[QualityReviewResponse],
    summary="提交 AI 整体质量评价",
)
def submit_quality_review(
    req: QualityReviewRequest,
    db: DbSession,
) -> dict:
    """保存或更新 AI 对话质量与 AI 评估质量两组维度评分。"""
    return ok(quality_review_service.submit_quality_review(db, req))


@router.get(
    "/api/quality-reviews/{task_id}",
    response_model=ApiResponse[QualityReviewResponse | None],
    summary="查询任务整体质量评价",
)
def get_quality_review(
    task_id: str,
    db: DbSession,
    reviewer_id: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """读取指定护士对任务的整体质量评价。"""
    return ok(quality_review_service.get_quality_review(db, task_id, reviewer_id))
