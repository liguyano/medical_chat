"""评估任务路由
作用：提供任务创建与详情查询接口，返回裸载荷以对齐前端 apiRepository。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.task import BackendTaskDto, CreateTaskRequest, CreateTaskResponse
from app.services import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", summary="创建评估任务")
def create_task(
    req: CreateTaskRequest, db: Session = Depends(get_db)
) -> CreateTaskResponse:
    """创建评估任务
    Args:
        - req: 创建任务请求
        - db: 数据库会话
    Return:
        - CreateTaskResponse: 任务创建响应（裸载荷）
    """
    return task_service.create_task(db, req)


@router.get("/{task_no}", summary="获取任务详情")
def get_task(task_no: str, db: Session = Depends(get_db)) -> BackendTaskDto:
    """获取任务详情
    Args:
        - task_no: 任务编号
        - db: 数据库会话
    Return:
        - BackendTaskDto: 任务详情（裸载荷）
    """
    return task_service.get_task(db, task_no)
