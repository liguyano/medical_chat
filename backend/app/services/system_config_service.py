"""Demo 系统配置服务
作用：提供宣教材料、拦截特征字典和量表当前版本的直接查看与更新。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.managers.keyword_matcher import get_keyword_matcher
from medagent.agents.service_agent.extraction_agent.types import normalize_answer_type
from app.models.assessment_template import (
    AssessmentActionDefinition,
    AssessmentOption,
    AssessmentQuestion,
    AssessmentRule,
    AssessmentScale,
    AssessmentScaleVersion,
    AssessmentSection,
)
from app.models.education import (
    EducationProgram,
    EducationProgramVersion,
    EducationUnit,
)
from app.models.interaction import InteractionRule
from app.schemas.system_config import (
    AssessmentActionConfigDto,
    AssessmentOptionConfigDto,
    AssessmentQuestionConfigDto,
    AssessmentRuleConfigDto,
    AssessmentScaleConfigDetailDto,
    AssessmentScaleConfigSummaryDto,
    AssessmentScaleConfigUpdateRequest,
    AssessmentSectionConfigDto,
    EducationMaterialConfigDto,
    EducationMaterialUpdateRequest,
    InteractionRuleConfigDto,
    InteractionRuleMatchDto,
    InteractionRuleUpdateRequest,
)


def _normalize_scale_snapshot(value: Any) -> Any:
    """归一化量表快照中的字段类型，避免旧别名再次落库。"""
    if isinstance(value, list):
        return [_normalize_scale_snapshot(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"type", "answer_type"} and isinstance(item, str):
            try:
                normalized[key] = normalize_answer_type(item)
            except ValueError:
                normalized[key] = item
        else:
            normalized[key] = _normalize_scale_snapshot(item)
    return normalized


def _content_hash(payload: dict[str, Any]) -> str:
    """计算配置内容哈希。"""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _risk_to_priority(risk_level: str) -> str:
    """把数据库风险等级转换为前端优先级。"""
    return {
        "normal": "low",
        "important": "medium",
        "high_risk": "high",
    }.get(risk_level, "medium")


def _priority_to_risk(priority: str) -> str:
    """把前端优先级转换为数据库风险等级。"""
    return {
        "low": "normal",
        "medium": "important",
        "high": "high_risk",
    }[priority]


def _current_education_rows(
    db: Session,
    *,
    program_id: int | None = None,
    category: str | None = None,
    active_only: bool = False,
) -> list[tuple[EducationProgram, EducationProgramVersion, EducationUnit]]:
    """查询宣教方案的最新版本和内容单元。"""
    latest_version = (
        select(
            EducationProgramVersion.program_id,
            func.max(EducationProgramVersion.id).label("version_id"),
        )
        .where(EducationProgramVersion.deleted == 0)
        .group_by(EducationProgramVersion.program_id)
        .subquery()
    )
    statement = (
        select(EducationProgram, EducationProgramVersion, EducationUnit)
        .join(latest_version, latest_version.c.program_id == EducationProgram.id)
        .join(
            EducationProgramVersion,
            EducationProgramVersion.id == latest_version.c.version_id,
        )
        .join(
            EducationUnit,
            EducationUnit.program_version_id == EducationProgramVersion.id,
        )
        .where(
            EducationProgram.deleted == 0,
            EducationUnit.deleted == 0,
        )
        .order_by(EducationProgram.id.asc(), EducationUnit.sort_no.asc())
    )
    if program_id is not None:
        statement = statement.where(EducationProgram.id == program_id)
    if category is not None:
        statement = statement.where(EducationProgram.program_code == category)
    if active_only:
        statement = statement.where(
            EducationProgram.status == "active",
            EducationProgramVersion.publish_status == "published",
        )
    return list(db.execute(statement).all())


def _education_dto(
    program: EducationProgram,
    version: EducationProgramVersion,
    unit: EducationUnit,
) -> EducationMaterialConfigDto:
    """组装宣教材料扁平 DTO。"""
    snapshot = version.content_snapshot or {}
    return EducationMaterialConfigDto(
        id=program.id,
        version_id=version.id,
        unit_id=unit.id,
        category=program.program_code,
        title=unit.unit_title,
        document_version=version.version_code,
        original_content=unit.original_text,
        patient_content=unit.patient_text,
        spoken_content=unit.voice_text,
        source_name=(
            str(snapshot["source_name"]) if snapshot.get("source_name") else None
        ),
        priority=_risk_to_priority(unit.risk_level),
        requires_acknowledgement=bool(
            snapshot.get("requires_acknowledgement", unit.mandatory)
        ),
        auto_play=bool(snapshot.get("auto_play", True)),
        enabled=(
            program.status == "active"
            and version.publish_status == "published"
        ),
    )


def list_education_materials(db: Session) -> list[EducationMaterialConfigDto]:
    """查询全部宣教材料。"""
    return [_education_dto(*row) for row in _current_education_rows(db)]


def update_education_material(
    db: Session,
    material_id: int,
    request: EducationMaterialUpdateRequest,
    *,
    operator: str,
) -> EducationMaterialConfigDto:
    """直接更新一条宣教材料并立即生效。"""
    rows = _current_education_rows(db, program_id=material_id)
    if not rows:
        raise AppError(ErrorCode.ERR_COMMON_001, "宣教材料不存在")
    program, version, unit = rows[0]
    program.program_name = request.title
    program.status = "active" if request.enabled else "inactive"
    program.updator = operator
    version.version_code = request.document_version
    version.publish_status = "published" if request.enabled else "disabled"
    version.content_snapshot = {
        "source_name": request.source_name,
        "requires_acknowledgement": request.requires_acknowledgement,
        "auto_play": request.auto_play,
    }
    version.content_hash = _content_hash(
        {
            **version.content_snapshot,
            "title": request.title,
            "document_version": request.document_version,
            "original_content": request.original_content,
            "patient_content": request.patient_content,
            "spoken_content": request.spoken_content,
            "priority": request.priority,
        }
    )
    version.updator = operator
    unit.unit_title = request.title
    unit.original_text = request.original_content
    unit.patient_text = request.patient_content
    unit.voice_text = request.spoken_content
    unit.mandatory = int(request.requires_acknowledgement)
    unit.risk_level = _priority_to_risk(request.priority)
    unit.updator = operator
    db.commit()
    return _education_dto(program, version, unit)


def get_education_tool_result(
    db: Session,
    *,
    category: str,
    level: int,
) -> dict[str, Any]:
    """读取当前生效宣教材料并转换为 Dialog 工具结果。"""
    rows = _current_education_rows(db, category=category, active_only=True)
    if not rows:
        return {"success": False, "message": f"未找到已启用的宣教材料: {category}"}
    dto = _education_dto(*rows[0])
    return {
        "success": True,
        "event_id": f"EDU-EVENT-{uuid.uuid4().hex.upper()}",
        "material_id": (
            f"EDU-{dto.category.upper()}-V{dto.document_version}-L{level}"
        ),
        "category": dto.category,
        "level": level,
        "document_version": dto.document_version,
        "title": dto.title,
        "original_content": dto.original_content,
        "patient_content": dto.patient_content,
        "spoken_content": dto.spoken_content,
        "content": dto.original_content,
        "audio_url": None,
        "source_name": dto.source_name,
        "priority": dto.priority,
        "requires_acknowledgement": dto.requires_acknowledgement,
        "auto_play": dto.auto_play,
        "teachback_required": True,
        "teachback_prompt": "请在宣教后邀请患者用自己的话复述最重要的提醒，确认理解后再继续评估。",
        "clinical_review_status": "demo_config",
    }


def _rule_dto(rule: InteractionRule) -> InteractionRuleConfigDto:
    """组装拦截特征规则 DTO。"""
    condition = rule.trigger_condition or {}
    action = rule.action_payload or {}
    return InteractionRuleConfigDto(
        id=rule.id,
        rule_code=rule.rule_code,
        rule_name=rule.rule_name,
        scope_type=rule.scope_type,
        scope_id=rule.scope_id,
        keywords=[str(item) for item in condition.get("keywords", [])],
        patterns=[str(item) for item in condition.get("patterns", [])],
        action_type=rule.action_type,
        prompt=str(action.get("prompt") or ""),
        tags=[str(item) for item in action.get("tags", [])],
        priority=rule.priority,
        enabled=rule.status == "active",
    )


def list_interaction_rules(db: Session) -> list[InteractionRuleConfigDto]:
    """查询全部拦截特征规则。"""
    rows = list(
        db.scalars(
            select(InteractionRule)
            .where(InteractionRule.deleted == 0)
            .order_by(InteractionRule.priority.desc(), InteractionRule.id.asc())
        ).all()
    )
    return [_rule_dto(row) for row in rows]


def _validate_patterns(patterns: list[str]) -> None:
    """校验正则表达式，阻止无效配置进入数据库。"""
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise AppError(
                ErrorCode.ERR_COMMON_001,
                f"正则表达式无效：{pattern}（{exc}）",
            ) from exc


def update_interaction_rule(
    db: Session,
    rule_id: int,
    request: InteractionRuleUpdateRequest,
    *,
    operator: str,
) -> InteractionRuleConfigDto:
    """直接更新拦截特征规则并刷新当前进程缓存。"""
    _validate_patterns(request.patterns)
    row = db.get(InteractionRule, rule_id)
    if row is None or row.deleted:
        raise AppError(ErrorCode.ERR_COMMON_001, "拦截规则不存在")
    row.rule_name = request.rule_name
    row.scope_type = request.scope_type
    row.scope_id = request.scope_id
    row.trigger_condition = {
        "keywords": request.keywords,
        "patterns": request.patterns,
    }
    row.action_type = request.action_type
    row.action_payload = {
        "prompt": request.prompt,
        "tags": request.tags,
    }
    row.priority = request.priority
    row.status = "active" if request.enabled else "inactive"
    row.updator = operator
    db.commit()
    get_keyword_matcher().load_rules(force=True)
    return _rule_dto(row)


def test_interaction_rules(text: str) -> list[InteractionRuleMatchDto]:
    """使用当前数据库规则测试一句患者文本。"""
    matcher = get_keyword_matcher()
    matcher.load_rules(force=True)
    return [
        InteractionRuleMatchDto(
            rule_code=item.rule_code,
            rule_name=item.rule_name,
            matched_terms=item.matched_terms,
            action_type=item.action_type,
            prompt=item.constraint_prompt,
            priority=item.priority,
        )
        for item in matcher.match(text)
    ]


def _current_scale_version(
    db: Session,
    scale_id: int,
) -> tuple[AssessmentScale, AssessmentScaleVersion]:
    """加载量表及其最新版本。"""
    row = db.execute(
        select(AssessmentScale, AssessmentScaleVersion)
        .join(
            AssessmentScaleVersion,
            AssessmentScaleVersion.scale_id == AssessmentScale.id,
        )
        .where(
            AssessmentScale.id == scale_id,
            AssessmentScale.deleted == 0,
            AssessmentScaleVersion.deleted == 0,
        )
        .order_by(AssessmentScaleVersion.id.desc())
    ).first()
    if row is None:
        raise AppError(ErrorCode.ERR_COMMON_001, "评估量表不存在")
    return row


def _count_rows(db: Session, model: Any, version_id: int) -> int:
    """统计某版本的一类配置记录。"""
    return int(
        db.scalar(
            select(func.count(model.id)).where(
                model.scale_version_id == version_id,
                model.deleted == 0,
            )
        )
        or 0
    )


def list_scale_configs(db: Session) -> list[AssessmentScaleConfigSummaryDto]:
    """查询全部量表当前版本摘要。"""
    scales = list(
        db.scalars(
            select(AssessmentScale)
            .where(AssessmentScale.deleted == 0)
            .order_by(AssessmentScale.id.asc())
        ).all()
    )
    result: list[AssessmentScaleConfigSummaryDto] = []
    for scale in scales:
        _, version = _current_scale_version(db, scale.id)
        result.append(
            AssessmentScaleConfigSummaryDto(
                id=scale.id,
                scale_code=scale.scale_code,
                scale_name=scale.scale_name,
                scale_type=scale.scale_type,
                clinical_purpose=scale.clinical_purpose,
                status=scale.status,
                version_id=version.id,
                version_code=version.version_code,
                version_name=version.version_name,
                publish_status=version.publish_status,
                section_count=_count_rows(db, AssessmentSection, version.id),
                question_count=_count_rows(db, AssessmentQuestion, version.id),
                option_count=int(
                    db.scalar(
                        select(func.count(AssessmentOption.id))
                        .join(
                            AssessmentQuestion,
                            AssessmentQuestion.id == AssessmentOption.question_id,
                        )
                        .where(
                            AssessmentQuestion.scale_version_id == version.id,
                            AssessmentQuestion.deleted == 0,
                            AssessmentOption.deleted == 0,
                        )
                    )
                    or 0
                ),
                rule_count=_count_rows(db, AssessmentRule, version.id),
                action_count=_count_rows(
                    db,
                    AssessmentActionDefinition,
                    version.id,
                ),
            )
        )
    return result


def get_scale_config(db: Session, scale_id: int) -> AssessmentScaleConfigDetailDto:
    """查询量表当前版本完整配置。"""
    scale, version = _current_scale_version(db, scale_id)
    sections = list(
        db.scalars(
            select(AssessmentSection)
            .where(
                AssessmentSection.scale_version_id == version.id,
                AssessmentSection.deleted == 0,
            )
            .order_by(AssessmentSection.sort_no.asc(), AssessmentSection.id.asc())
        ).all()
    )
    questions = list(
        db.scalars(
            select(AssessmentQuestion)
            .where(
                AssessmentQuestion.scale_version_id == version.id,
                AssessmentQuestion.deleted == 0,
            )
            .order_by(AssessmentQuestion.sort_no.asc(), AssessmentQuestion.id.asc())
        ).all()
    )
    question_ids = [item.id for item in questions]
    options = (
        list(
            db.scalars(
                select(AssessmentOption)
                .where(
                    AssessmentOption.question_id.in_(question_ids),
                    AssessmentOption.deleted == 0,
                )
                .order_by(AssessmentOption.question_id, AssessmentOption.sort_no)
            ).all()
        )
        if question_ids
        else []
    )
    rules = list(
        db.scalars(
            select(AssessmentRule)
            .where(
                AssessmentRule.scale_version_id == version.id,
                AssessmentRule.deleted == 0,
            )
            .order_by(AssessmentRule.priority.desc(), AssessmentRule.id.asc())
        ).all()
    )
    actions = list(
        db.scalars(
            select(AssessmentActionDefinition)
            .where(
                AssessmentActionDefinition.scale_version_id == version.id,
                AssessmentActionDefinition.deleted == 0,
            )
            .order_by(
                AssessmentActionDefinition.sort_no.asc(),
                AssessmentActionDefinition.id.asc(),
            )
        ).all()
    )
    return AssessmentScaleConfigDetailDto(
        id=scale.id,
        scale_code=scale.scale_code,
        scale_name=scale.scale_name,
        scale_type=scale.scale_type,
        clinical_purpose=scale.clinical_purpose,
        applicable_scope=scale.applicable_scope,
        source_file=scale.source_file,
        status=scale.status,
        version_id=version.id,
        version_code=version.version_code,
        version_name=version.version_name,
        publish_status=version.publish_status,
        scale_snapshot=version.scale_snapshot or {},
        sections=[
            AssessmentSectionConfigDto(
                id=item.id,
                parent_section_id=item.parent_section_id,
                section_code=item.section_code,
                section_name=item.section_name,
                section_description=item.section_description,
                display_condition=item.display_condition,
                sort_no=item.sort_no,
            )
            for item in sections
        ],
        questions=[
            AssessmentQuestionConfigDto(
                id=item.id,
                section_id=item.section_id,
                question_code=item.question_code,
                question_name=item.question_name,
                original_text=item.original_text,
                patient_text=item.patient_text,
                nurse_text=item.nurse_text,
                question_type=item.question_type,
                value_type=item.value_type,
                required=item.required,
                scored=item.scored,
                unit=item.unit,
                value_precision=item.value_precision,
                allow_other=item.allow_other,
                derived=item.derived,
                calculation_expression=item.calculation_expression,
                validation_rule=item.validation_rule,
                sort_no=item.sort_no,
            )
            for item in questions
        ],
        options=[
            AssessmentOptionConfigDto(
                id=item.id,
                question_id=item.question_id,
                option_code=item.option_code,
                option_label=item.option_label,
                option_value=item.option_value,
                clinical_score=(
                    float(item.clinical_score)
                    if item.clinical_score is not None
                    else None
                ),
                risk_tag=item.risk_tag,
                requires_follow_up=item.requires_follow_up,
                extra_input_type=item.extra_input_type,
                extra_input_unit=item.extra_input_unit,
                sort_no=item.sort_no,
            )
            for item in options
        ],
        rules=[
            AssessmentRuleConfigDto(
                id=item.id,
                rule_code=item.rule_code,
                rule_type=item.rule_type,
                condition_expression=item.condition_expression,
                result_payload=item.result_payload,
                priority=item.priority,
                status=item.status,
            )
            for item in rules
        ],
        actions=[
            AssessmentActionConfigDto(
                id=item.id,
                action_code=item.action_code,
                action_group=item.action_group,
                action_name=item.action_name,
                action_type=item.action_type,
                input_type=item.input_type,
                allow_other=item.allow_other,
                trigger_rule_id=item.trigger_rule_id,
                sort_no=item.sort_no,
            )
            for item in actions
        ],
    )


def _require_same_ids(
    *,
    label: str,
    requested: list[Any],
    existing: list[Any],
) -> None:
    """Demo 编辑只允许修改已有行，不允许通过 JSON 意外增删配置。"""
    requested_ids = {int(item.id) for item in requested}
    existing_ids = {int(item.id) for item in existing}
    if requested_ids != existing_ids:
        raise AppError(
            ErrorCode.ERR_COMMON_001,
            f"{label}记录编号不完整或包含无效编号，本功能只允许编辑已有配置",
        )


def update_scale_config(
    db: Session,
    scale_id: int,
    request: AssessmentScaleConfigUpdateRequest,
    *,
    operator: str,
) -> AssessmentScaleConfigDetailDto:
    """直接更新量表当前版本及其已有子配置。"""
    scale, version = _current_scale_version(db, scale_id)
    if request.id != scale.id or request.version_id != version.id:
        raise AppError(ErrorCode.ERR_COMMON_001, "量表或版本编号不匹配")
    if (
        request.scale_code != scale.scale_code
        or request.version_code != version.version_code
    ):
        raise AppError(ErrorCode.ERR_COMMON_001, "量表编码和版本编码不允许修改")

    existing = get_scale_config(db, scale_id)
    _require_same_ids(
        label="分组",
        requested=request.sections,
        existing=existing.sections,
    )
    _require_same_ids(
        label="问题",
        requested=request.questions,
        existing=existing.questions,
    )
    _require_same_ids(
        label="选项",
        requested=request.options,
        existing=existing.options,
    )
    _require_same_ids(
        label="规则",
        requested=request.rules,
        existing=existing.rules,
    )
    _require_same_ids(
        label="护理措施",
        requested=request.actions,
        existing=existing.actions,
    )

    scale.scale_name = request.scale_name
    scale.scale_type = request.scale_type
    scale.clinical_purpose = request.clinical_purpose
    scale.applicable_scope = request.applicable_scope
    scale.source_file = request.source_file
    scale.status = request.status
    scale.updator = operator
    version.version_name = request.version_name
    version.publish_status = request.publish_status
    version.scale_snapshot = _normalize_scale_snapshot(request.scale_snapshot)
    version.content_hash = _content_hash(request.model_dump(mode="json"))
    version.updator = operator

    section_ids = {item.id for item in request.sections}
    question_ids = {item.id for item in request.questions}
    rule_ids = {item.id for item in request.rules}
    for item in request.sections:
        row = db.get(AssessmentSection, item.id)
        if row is None:
            continue
        if item.parent_section_id is not None and item.parent_section_id not in section_ids:
            raise AppError(ErrorCode.ERR_COMMON_001, "分组父级不属于当前量表")
        row.parent_section_id = item.parent_section_id
        row.section_code = item.section_code
        row.section_name = item.section_name
        row.section_description = item.section_description
        row.display_condition = item.display_condition
        row.sort_no = item.sort_no
        row.updator = operator

    for item in request.questions:
        row = db.get(AssessmentQuestion, item.id)
        if row is None:
            continue
        if item.section_id is not None and item.section_id not in section_ids:
            raise AppError(ErrorCode.ERR_COMMON_001, "问题分组不属于当前量表")
        row.section_id = item.section_id
        row.question_code = item.question_code
        row.question_name = item.question_name
        row.original_text = item.original_text
        row.patient_text = item.patient_text
        row.nurse_text = item.nurse_text
        try:
            row.question_type = normalize_answer_type(item.question_type)
        except ValueError as exc:
            raise AppError(ErrorCode.ERR_COMMON_001, str(exc)) from exc
        value_type_map = {
            "字符串": "string",
            "整数": "number",
            "小数": "number",
            "布尔": "boolean",
            "日期": "date",
            "日期时间": "date",
            "text": "string",
            "number": "number",
            "boolean": "boolean",
            "date": "date",
            "string": "string",
        }
        normalized_value_type = value_type_map.get(item.value_type)
        if normalized_value_type is None:
            raise AppError(
                ErrorCode.ERR_COMMON_001,
                f"不支持的值类型: {item.value_type}",
            )
        row.value_type = normalized_value_type
        row.required = item.required
        row.scored = item.scored
        row.unit = item.unit
        row.value_precision = item.value_precision
        row.allow_other = item.allow_other
        row.derived = item.derived
        row.calculation_expression = item.calculation_expression
        row.validation_rule = item.validation_rule
        row.sort_no = item.sort_no
        row.updator = operator

    for item in request.options:
        row = db.get(AssessmentOption, item.id)
        if row is None:
            continue
        if item.question_id not in question_ids:
            raise AppError(ErrorCode.ERR_COMMON_001, "选项问题不属于当前量表")
        row.question_id = item.question_id
        row.option_code = item.option_code
        row.option_label = item.option_label
        row.option_value = item.option_value
        row.clinical_score = item.clinical_score
        row.risk_tag = item.risk_tag
        row.requires_follow_up = item.requires_follow_up
        row.extra_input_type = item.extra_input_type
        row.extra_input_unit = item.extra_input_unit
        row.sort_no = item.sort_no
        row.updator = operator

    for item in request.rules:
        row = db.get(AssessmentRule, item.id)
        if row is None:
            continue
        row.rule_code = item.rule_code
        row.rule_type = item.rule_type
        row.condition_expression = item.condition_expression
        row.result_payload = item.result_payload
        row.priority = item.priority
        row.status = item.status
        row.updator = operator

    for item in request.actions:
        row = db.get(AssessmentActionDefinition, item.id)
        if row is None:
            continue
        if item.trigger_rule_id is not None and item.trigger_rule_id not in rule_ids:
            raise AppError(ErrorCode.ERR_COMMON_001, "护理措施触发规则不属于当前量表")
        row.action_code = item.action_code
        row.action_group = item.action_group
        row.action_name = item.action_name
        row.action_type = item.action_type
        row.input_type = item.input_type
        row.allow_other = item.allow_other
        row.trigger_rule_id = item.trigger_rule_id
        row.sort_no = item.sort_no
        row.updator = operator

    db.commit()
    return get_scale_config(db, scale_id)
