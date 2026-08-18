"""量表路由
作用：提供已发布量表查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_staff
from app.models.base import get_db
from app.models.staff_account import StaffAccount
from app.schemas.response import ApiResponse, ok
from app.schemas.scale import AssessmentScaleDto
from app.services import scale_service

router = APIRouter(prefix="/api/scales", tags=["scales"])


@router.get(
    "",
    response_model=ApiResponse[list[AssessmentScaleDto]],
    summary="查询已发布量表列表",
)
def list_published_scales(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[StaffAccount, Depends(require_staff)],
) -> dict:
    """查询已发布量表列表
    作用：返回当前生效且已发布的量表版本，含非衍生题目计数。
    Args:
        - db: 数据库会话
    Return:
        - 已发布量表列表
    """
    return ok(scale_service.list_published_scales(db))
