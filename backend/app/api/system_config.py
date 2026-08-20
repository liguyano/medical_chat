"""Demo 系统配置路由
作用：提供宣教材料、拦截特征字典和评估量表的查看与直接更新接口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_staff
from app.models.base import get_db
from app.models.staff_account import StaffAccount
from app.schemas.response import ApiResponse, ok
from app.schemas.system_config import (
    AssessmentScaleConfigDetailDto,
    AssessmentScaleConfigSummaryDto,
    AssessmentScaleConfigUpdateRequest,
    EducationMaterialConfigDto,
    EducationMaterialUpdateRequest,
    InteractionRuleConfigDto,
    InteractionRuleMatchDto,
    InteractionRuleTestRequest,
    InteractionRuleUpdateRequest,
)
from app.services import system_config_service

router = APIRouter(prefix="/api/system-config", tags=["system-config"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentStaff = Annotated[StaffAccount, Depends(require_staff)]


@router.get(
    "/education-materials",
    response_model=ApiResponse[list[EducationMaterialConfigDto]],
    summary="查询宣教材料配置",
)
def list_education_materials(db: DbSession, _: CurrentStaff) -> dict:
    """查询全部 Demo 宣教材料。"""
    return ok(system_config_service.list_education_materials(db))


@router.put(
    "/education-materials/{material_id}",
    response_model=ApiResponse[EducationMaterialConfigDto],
    summary="直接更新宣教材料",
)
def update_education_material(
    material_id: int,
    request: EducationMaterialUpdateRequest,
    db: DbSession,
    staff: CurrentStaff,
) -> dict:
    """直接保存宣教材料并立即供新工具调用使用。"""
    return ok(
        system_config_service.update_education_material(
            db,
            material_id,
            request,
            operator=staff.staff_no,
        )
    )


@router.get(
    "/interaction-rules",
    response_model=ApiResponse[list[InteractionRuleConfigDto]],
    summary="查询拦截特征字典",
)
def list_interaction_rules(db: DbSession, _: CurrentStaff) -> dict:
    """查询全部关键词和正则拦截规则。"""
    return ok(system_config_service.list_interaction_rules(db))


@router.put(
    "/interaction-rules/{rule_id}",
    response_model=ApiResponse[InteractionRuleConfigDto],
    summary="直接更新拦截特征规则",
)
def update_interaction_rule(
    rule_id: int,
    request: InteractionRuleUpdateRequest,
    db: DbSession,
    staff: CurrentStaff,
) -> dict:
    """直接保存拦截规则并刷新当前运行时缓存。"""
    return ok(
        system_config_service.update_interaction_rule(
            db,
            rule_id,
            request,
            operator=staff.staff_no,
        )
    )


@router.post(
    "/interaction-rules/test",
    response_model=ApiResponse[list[InteractionRuleMatchDto]],
    summary="测试拦截特征命中",
)
def test_interaction_rules(
    request: InteractionRuleTestRequest,
    _: CurrentStaff,
) -> dict:
    """使用当前数据库规则测试一段患者文本。"""
    return ok(system_config_service.test_interaction_rules(request.text))


@router.get(
    "/scales",
    response_model=ApiResponse[list[AssessmentScaleConfigSummaryDto]],
    summary="查询量表配置摘要",
)
def list_scale_configs(db: DbSession, _: CurrentStaff) -> dict:
    """查询全部量表及当前版本配置项数量。"""
    return ok(system_config_service.list_scale_configs(db))


@router.get(
    "/scales/{scale_id}",
    response_model=ApiResponse[AssessmentScaleConfigDetailDto],
    summary="查询量表完整配置",
)
def get_scale_config(scale_id: int, db: DbSession, _: CurrentStaff) -> dict:
    """查询量表当前版本的全部配置项。"""
    return ok(system_config_service.get_scale_config(db, scale_id))


@router.put(
    "/scales/{scale_id}",
    response_model=ApiResponse[AssessmentScaleConfigDetailDto],
    summary="直接更新量表完整配置",
)
def update_scale_config(
    scale_id: int,
    request: AssessmentScaleConfigUpdateRequest,
    db: DbSession,
    staff: CurrentStaff,
) -> dict:
    """直接更新量表及其已有配置项。"""
    return ok(
        system_config_service.update_scale_config(
            db,
            scale_id,
            request,
            operator=staff.staff_no,
        )
    )
