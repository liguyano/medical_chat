"""补齐患者端门户、知情同意与播报运行域。"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "20260822_patient_portal"
down_revision: str | Sequence[str] | None = "20260822_task_preparation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("creator", sa.String(64), nullable=True),
        sa.Column("updator", sa.String(64), nullable=True),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted", sa.Integer(), server_default="0", nullable=False),
    ]


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    """创建患者门户和知情同意相关业务表。"""
    op.create_table(
        "patient_notification",
        *_base(),
        sa.Column("notification_no", sa.String(64), nullable=False, unique=True),
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patient.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), sa.ForeignKey("patient_encounter.id", ondelete="SET NULL")),
        sa.Column("notification_type", sa.String(32), nullable=False, server_default="general"),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("payload", _json(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_patient_notification_owner", "patient_notification", ["patient_id", "encounter_id", "deleted"])
    op.create_index("idx_patient_notification_unread", "patient_notification", ["patient_id", "read_at", "deleted"])

    op.create_table(
        "ward_guide",
        *_base(),
        sa.Column("guide_code", sa.String(64), nullable=False, unique=True),
        sa.Column("department_code", sa.String(64)),
        sa.Column("department_name", sa.String(128)),
        sa.Column("ward_name", sa.String(128)),
        sa.Column("category", sa.String(64), nullable=False, server_default="住院生活"),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", _json(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="published"),
    )
    op.create_index("idx_ward_guide_scope", "ward_guide", ["department_code", "ward_name", "status", "deleted"])

    op.create_table(
        "patient_assistant_session",
        *_base(),
        sa.Column("session_no", sa.String(64), nullable=False, unique=True),
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patient.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), sa.ForeignKey("patient_encounter.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_type", sa.String(16), nullable=False, server_default="text"),
        sa.Column("session_status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("handoff_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("handoff_reason", sa.Text()),
    )
    op.create_index("idx_patient_assistant_owner", "patient_assistant_session", ["patient_id", "encounter_id", "deleted"])
    op.create_table(
        "patient_assistant_message",
        *_base(),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("patient_assistant_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_no", sa.String(64), nullable=False, unique=True),
        sa.Column("role_type", sa.String(16), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("result_status", sa.String(32)),
        sa.Column("source_guide_id", sa.BigInteger(), sa.ForeignKey("ward_guide.id", ondelete="SET NULL")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_patient_assistant_message_session", "patient_assistant_message", ["session_id", "occurred_at"])

    op.create_table(
        "consent_document",
        *_base(),
        sa.Column("consent_code", sa.String(64), nullable=False, unique=True),
        sa.Column("consent_name", sa.String(160), nullable=False),
        sa.Column("consent_type", sa.String(64), nullable=False),
        sa.Column("source_file", sa.String(512)),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    op.create_table(
        "consent_document_version",
        *_base(),
        sa.Column("consent_document_id", sa.BigInteger(), sa.ForeignKey("consent_document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_code", sa.String(64), nullable=False),
        sa.Column("publish_status", sa.String(32), nullable=False, server_default="published"),
        sa.Column("effective_time", sa.DateTime(timezone=True)),
        sa.Column("expire_time", sa.DateTime(timezone=True)),
        sa.Column("full_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(128), nullable=False, server_default=""),
        sa.UniqueConstraint("consent_document_id", "version_code", name="uq_consent_document_version"),
    )
    op.create_index("idx_consent_version_publish", "consent_document_version", ["consent_document_id", "publish_status", "deleted"])
    op.create_table(
        "consent_clause",
        *_base(),
        sa.Column("consent_version_id", sa.BigInteger(), sa.ForeignKey("consent_document_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_code", sa.String(64), nullable=False),
        sa.Column("clause_title", sa.String(160), nullable=False),
        sa.Column("original_content", sa.Text(), nullable=False),
        sa.Column("patient_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("voice_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("audio_url", sa.String(512)),
        sa.Column("audio_duration_seconds", sa.Integer()),
        sa.Column("importance_level", sa.String(32), nullable=False, server_default="一般"),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("teachback_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("consent_version_id", "clause_code", name="uq_consent_clause_code"),
    )
    op.create_index("idx_consent_clause_sort", "consent_clause", ["consent_version_id", "sort_no", "deleted"])
    op.create_table(
        "consent_record",
        *_base(),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("care_task.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patient.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), sa.ForeignKey("patient_encounter.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consent_document_id", sa.BigInteger(), sa.ForeignKey("consent_document.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("consent_version_id", sa.BigInteger(), sa.ForeignKey("consent_document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("interaction_session_id", sa.BigInteger(), sa.ForeignKey("interaction_session.id", ondelete="SET NULL")),
        sa.Column("participant_type", sa.String(32), nullable=False, server_default="patient"),
        sa.Column("record_status", sa.String(32), nullable=False, server_default="进行中"),
        sa.Column("patient_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("nurse_confirmed_by", sa.BigInteger()),
        sa.UniqueConstraint("task_id", "consent_version_id", name="uq_consent_record_task_version"),
    )
    op.create_index("idx_consent_record_patient", "consent_record", ["patient_id", "encounter_id", "deleted"])
    op.create_table(
        "consent_clause_record",
        *_base(),
        sa.Column("consent_record_id", sa.BigInteger(), sa.ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", sa.BigInteger(), sa.ForeignKey("consent_clause.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_reply_message_id", sa.BigInteger(), sa.ForeignKey("interaction_message.id", ondelete="SET NULL")),
        sa.Column("confirmation_result", sa.String(32), nullable=False),
        sa.Column("patient_reply", sa.Text()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("need_nurse_explain", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("consent_record_id", "clause_id", name="uq_consent_clause_record"),
    )
    op.create_table(
        "consent_record_item",
        *_base(),
        sa.Column("consent_record_id", sa.BigInteger(), sa.ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False),
        sa.Column("item_name", sa.String(160), nullable=False),
        sa.Column("item_content", sa.Text()),
        sa.Column("patient_decision", sa.String(32)),
        sa.Column("patient_comment", sa.Text()),
    )
    op.create_table(
        "consent_participant",
        *_base(),
        sa.Column("consent_record_id", sa.BigInteger(), sa.ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_type", sa.String(32), nullable=False),
        sa.Column("participant_name", sa.String(128), nullable=False),
        sa.Column("relationship_to_patient", sa.String(64)),
        sa.Column("id_card_masked", sa.String(64)),
        sa.Column("contact_phone_masked", sa.String(64)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "consent_authorization",
        *_base(),
        sa.Column("consent_record_id", sa.BigInteger(), sa.ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("principal_name", sa.String(128), nullable=False),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("relationship_to_patient", sa.String(64), nullable=False),
        sa.Column("authorization_reason", sa.Text()),
        sa.Column("authorization_file_url", sa.String(512)),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "consent_signature",
        *_base(),
        sa.Column("consent_record_id", sa.BigInteger(), sa.ForeignKey("consent_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_id", sa.BigInteger(), sa.ForeignKey("consent_participant.id", ondelete="SET NULL")),
        sa.Column("signer_type", sa.String(32), nullable=False),
        sa.Column("signer_name_snapshot", sa.String(128), nullable=False),
        sa.Column("signature_method", sa.String(32), nullable=False),
        sa.Column("signature_file_url", sa.String(512)),
        sa.Column("signed_content_hash", sa.String(128)),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_consent_signature_record", "consent_signature", ["consent_record_id", "deleted"])

    op.create_table(
        "content_delivery_session",
        *_base(),
        sa.Column("patient_id", sa.BigInteger(), sa.ForeignKey("patient.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encounter_id", sa.BigInteger(), sa.ForeignKey("patient_encounter.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_type", sa.String(32), nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_type", sa.String(16), nullable=False, server_default="voice"),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "content_delivery_item",
        *_base(),
        sa.Column("delivery_session_id", sa.BigInteger(), sa.ForeignKey("content_delivery_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("original_text_snapshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("patient_text_snapshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("voice_text_snapshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("audio_url", sa.String(512)),
        sa.Column("audio_duration_seconds", sa.Integer()),
        sa.Column("position_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("playback_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("patient_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "content_playback_event",
        *_base(),
        sa.Column("delivery_item_id", sa.BigInteger(), sa.ForeignKey("content_delivery_item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("position_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_invocation_id", sa.String(128)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("delivery_item_id", "client_invocation_id", name="uq_content_playback_invocation"),
    )


def downgrade() -> None:
    """按依赖顺序移除患者门户补充域。"""
    op.drop_table("content_playback_event")
    op.drop_table("content_delivery_item")
    op.drop_table("content_delivery_session")
    op.drop_index("idx_consent_signature_record", table_name="consent_signature")
    op.drop_table("consent_signature")
    op.drop_table("consent_authorization")
    op.drop_table("consent_participant")
    op.drop_table("consent_record_item")
    op.drop_table("consent_clause_record")
    op.drop_index("idx_consent_record_patient", table_name="consent_record")
    op.drop_table("consent_record")
    op.drop_index("idx_consent_clause_sort", table_name="consent_clause")
    op.drop_table("consent_clause")
    op.drop_index("idx_consent_version_publish", table_name="consent_document_version")
    op.drop_table("consent_document_version")
    op.drop_table("consent_document")
    op.drop_index("idx_patient_assistant_message_session", table_name="patient_assistant_message")
    op.drop_table("patient_assistant_message")
    op.drop_index("idx_patient_assistant_owner", table_name="patient_assistant_session")
    op.drop_table("patient_assistant_session")
    op.drop_index("idx_ward_guide_scope", table_name="ward_guide")
    op.drop_table("ward_guide")
    op.drop_index("idx_patient_notification_unread", table_name="patient_notification")
    op.drop_index("idx_patient_notification_owner", table_name="patient_notification")
    op.drop_table("patient_notification")
