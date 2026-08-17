"""量表相关 Schema
作用：定义量表查询响应结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssessmentScaleDto(BaseModel):
    """量表响应 DTO
    作用：与前端 AssessmentScale 类型对齐，含量表基本信息与题目计数。
    """

    id: int = Field(..., description="量表主键")
    scale_code: str = Field(..., description="量表编码（唯一）")
    scale_name: str = Field(..., description="量表名称")
    scale_type: str = Field(..., description="量表类型")
    question_count: int = Field(..., description="非衍生题目数（供前端显示）")
    version_code: str = Field(..., description="当前生效版本号")
    description: str | None = Field(default=None, description="量表描述")
