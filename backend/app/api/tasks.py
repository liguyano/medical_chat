"""评估任务路由
作用：提供任务创建与详情查询接口，返回统一 {code, message, data} 结构。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.schemas.response import ApiResponse, ok
from app.schemas.task import CreateTaskRequest, TaskResponse
from app.services import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=ApiResponse[TaskResponse], summary="创建评估任务")
def create_task(req: CreateTaskRequest, db: Session = Depends(get_db)) -> dict:
    """创建评估任务
    Args:
        - req: 创建任务请求
        - db: 数据库会话
    Return:
        - 统一响应，data 为任务详情
    """
    data = task_service.create_task(db, req)
    return ok(data)


@router.get("/{task_no}", response_model=ApiResponse[TaskResponse], summary="获取任务详情")
def get_task(task_no: str, db: Session = Depends(get_db)) -> dict:
    """获取任务详情
    Args:
        - task_no: 任务编号
        - db: 数据库会话
    Return:
        - 统一响应，data 为任务详情
    """
    data = task_service.get_task(db, task_no)
    return ok(data)
