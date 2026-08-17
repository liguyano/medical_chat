"""评估任务路由
作用：提供任务创建与详情查询接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.response import ApiResponse, ok
from app.schemas.task import BackendTaskDto, CreateTaskRequest, CreateTaskResponse
from app.services import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ApiResponse[CreateTaskResponse], summary="创建评估任务")
def create_task(req: CreateTaskRequest, db: DbSession) -> dict:
    """创建评估任务
    Args:
        - req: 创建任务请求
        - db: 数据库会话
    Return:
        - CreateTaskResponse: 任务创建响应（裸载荷）
    """
    return ok(task_service.create_task(db, req))


@router.get(
    "/{task_ref}",
    response_model=ApiResponse[BackendTaskDto],
    summary="获取任务详情",
)
def get_task(task_ref: str, db: DbSession) -> dict:
    """获取任务详情
    Args:
        - task_ref: 任务主键或任务编号
        - db: 数据库会话
    Return:
        - BackendTaskDto: 任务详情（裸载荷）
    """
    return ok(task_service.get_task(db, task_ref))
