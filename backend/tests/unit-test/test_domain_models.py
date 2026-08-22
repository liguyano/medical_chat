"""需求1批次 A ORM 元数据单元测试。"""
from sqlalchemy import UniqueConstraint

from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import Base, InteractionMessage

EXPECTED_TABLES = {
    "patient",
    "patient_encounter",
    "care_task",
    "assessment_scale",
    "assessment_scale_version",
    "assessment_section",
    "assessment_question",
    "assessment_option",
    "assessment_rule",
    "assessment_action_definition",
    "interaction_session",
    "interaction_message",
    "interaction_event",
    "interaction_rule",
    "dialogue_script",
    "interaction_message_feedback",
    "assessment_instance",
    "assessment_submission",
    "assessment_answer",
    "assessment_answer_option",
    "assessment_score",
    "assessment_review",
    "quality_review_template",
    "quality_review_dimension",
    "quality_review",
    "quality_review_score",
    "staff_account",
    "education_program",
    "education_program_version",
    "education_unit",
    "patient_profile_snapshot",
    "nursing_plan",
    "nursing_plan_item",
    "patient_notification",
    "ward_guide",
    "patient_assistant_session",
    "patient_assistant_message",
    "consent_document",
    "consent_document_version",
    "consent_clause",
    "consent_record",
    "consent_clause_record",
    "consent_record_item",
    "consent_participant",
    "consent_authorization",
    "consent_signature",
    "content_delivery_session",
    "content_delivery_item",
    "content_playback_event",
}

OBSOLETE_TABLES = {
    "assessment_tasks",
    "dialog_sessions",
    "dialog_messages",
    "dialog_turns",
    "extracted_fields",
    "agent_states",
    "nurse_ratings",
    "education_records",
    "consent_forms",
}


def test_quality_review_registers_all_domain_tables():
    """核心、患者门户、质量评价与护理计划域应准确注册全部领域表。"""
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert OBSOLETE_TABLES.isdisjoint(Base.metadata.tables)


def test_all_tables_have_unified_business_columns():
    """所有业务表必须具备统一审计与逻辑删除字段。"""
    common_columns = {"id", "creator", "updator", "create_time", "update_time", "deleted"}
    for table in Base.metadata.sorted_tables:
        assert common_columns.issubset(table.columns.keys()), table.name
        assert table.c.id.primary_key
        assert not table.c.create_time.nullable
        assert not table.c.update_time.nullable
        assert not table.c.deleted.nullable
        assert table.c.create_time.server_default is not None
        assert table.c.update_time.server_default is not None
        assert table.c.deleted.server_default is not None


def test_all_foreign_keys_resolve_to_registered_domain_tables():
    """所有已声明外键必须能解析到已注册领域表。"""
    for table in Base.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            assert foreign_key.column.table.name in EXPECTED_TABLES


def _unique_column_names(table_name: str, constraint_name: str) -> tuple[str, ...]:
    table = Base.metadata.tables[table_name]
    constraint = next(
        item
        for item in table.constraints
        if isinstance(item, UniqueConstraint) and item.name == constraint_name
    )
    return tuple(column.name for column in constraint.columns)


def test_human_ai_comparison_key_constraints():
    """多提交、人机对比、逐轮标注和整体质评的关键唯一约束必须存在。"""
    assert _unique_column_names(
        "assessment_answer",
        "uq_answer_submission_question",
    ) == ("submission_id", "question_id")
    assert _unique_column_names(
        "interaction_message_feedback",
        "uq_message_feedback_reviewer",
    ) == ("interaction_message_id", "reviewer_id")
    assert _unique_column_names(
        "assessment_scale_version",
        "uq_scale_version_code",
    ) == ("scale_id", "version_code")
    assert _unique_column_names(
        "quality_review_template",
        "uq_quality_review_template_code",
    ) == ("template_code", "version_code")
    assert _unique_column_names(
        "quality_review_dimension",
        "uq_quality_review_dimension_code",
    ) == ("template_id", "dimension_code")
    assert _unique_column_names(
        "quality_review_score",
        "uq_quality_review_score_dimension",
    ) == ("quality_review_id", "dimension_id")


def test_requirement_gap_fields_are_present():
    """需求1已确认的采集模式与进度字段必须落入 ORM。"""
    care_task = Base.metadata.tables["care_task"]
    submission = Base.metadata.tables["assessment_submission"]
    assert "collection_mode" in care_task.columns
    assert "total_question_count" in submission.columns
    assert "answered_question_count" in submission.columns


def test_langchain_format_maps_domain_roles():
    """对话管理器应将领域角色转换为 LangChain 角色。"""
    history = [
        InteractionMessage(role_type="AI", content_text="您好"),
        InteractionMessage(role_type="患者", content_text="你好"),
        InteractionMessage(role_type="系统", content_text="系统提示"),
    ]
    assert DialogHistoryManager.format_for_langchain(history) == [
        {"role": "assistant", "content": "您好"},
        {"role": "user", "content": "你好"},
        {"role": "system", "content": "系统提示"},
    ]
