"""医护账号 Schema。
作用：定义医护端登录请求、当前用户响应和登录响应结构。
"""

from pydantic import BaseModel, Field


class StaffLoginRequest(BaseModel):
    """医护账号登录请求。"""

    staff_no: str = Field(..., min_length=1, max_length=64, description="医护工号")
    password: str = Field(..., min_length=1, max_length=128, description="登录密码")


class StaffDto(BaseModel):
    """医护账号公开信息，不返回密码哈希。"""

    id: int = Field(..., description="医护账号主键")
    staff_no: str = Field(..., description="医护工号")
    staff_name: str = Field(..., description="医护姓名")
    role_code: str = Field(..., description="角色编码")
    department_name: str | None = Field(default=None, description="所属科室")


class StaffLoginResponse(BaseModel):
    """医护登录响应。"""

    staff: StaffDto
