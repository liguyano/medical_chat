"""字段抽取路由
作用：提供抽取字段查询接口。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.extraction import ExtractedFieldsResponse
from app.services import extraction_service

router = APIRouter(prefix="/api/extraction", tags=["extraction"])


@router.get("/{session_no}/fields", summary="查询会话抽取字段")
def get_extracted_fields(
    session_no: str,
    db: Session = Depends(get_db),
) -> ExtractedFieldsResponse:
    """查询会话抽取字段
    作用：返回指定会话的 AI 抽取结果（字段列表）。
    Args:
        - session_no: 会话编号
        - db: 数据库会话
    Return:
        - 抽取字段响应（含 session_id 与 fields 列表）
    """
    return extraction_service.get_extracted_fields(db, session_no)
