"""新增 Demo 宣教配置中心表并导入内置材料。

Revision ID: 20260820_demo_config
Revises: 20260818_staff_accounts
"""

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260820_demo_config"
down_revision: str | Sequence[str] | None = "20260818_staff_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _business_columns() -> list[sa.Column]:
    """返回模板表共用业务字段。"""
    return [
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("creator", sa.String(length=64), nullable=True),
        sa.Column("updator", sa.String(length=64), nullable=True),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "update_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "deleted",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    ]


_MATERIALS = [
    {
        "code": "tobacco",
        "name": "住院期间戒烟与烟草危害宣教",
        "original": (
            "吸烟会增加心脑血管疾病、呼吸系统疾病、伤口愈合不良和感染的风险。"
            "住院病区属于无烟环境，请勿在病房、卫生间、楼梯间等区域吸烟。"
            "如出现明显烦躁、失眠、头痛或强烈吸烟冲动，请告知医护人员，"
            "由医护人员评估是否需要进一步的戒烟支持。"
        ),
        "patient": (
            "住院期间请先不要吸烟，也不要在病房、卫生间或楼梯间吸烟。"
            "如果烟瘾明显、心里烦躁或睡不好，可以直接告诉护士，我们会协助您。"
        ),
        "voice": (
            "跟您提醒一下，住院期间请先不要吸烟，病房、卫生间和楼梯间也都是无烟区域。"
            "如果烟瘾明显，或者出现烦躁、睡不好等不舒服，请及时告诉护士。"
        ),
        "risk": "important",
    },
    {
        "code": "alcohol",
        "name": "饮酒风险与住院安全宣教",
        "original": (
            "饮酒可能影响血压、血糖、睡眠、肝功能以及部分药物的疗效和不良反应。"
            "住院期间请勿自行饮酒。长期大量饮酒者突然停止饮酒后，如出现手抖、"
            "明显出汗、心慌、烦躁、幻觉或抽搐，应立即告知医护人员。"
        ),
        "patient": (
            "住院期间请不要自行饮酒，因为酒精可能和药物相互影响。"
            "如果您平时饮酒较多，停酒后出现手抖、出汗、心慌、烦躁或看见异常事物，"
            "请马上呼叫护士。"
        ),
        "voice": (
            "住院期间请不要自行饮酒，以免影响用药和身体恢复。"
            "如果停酒后出现手抖、出汗、心慌、烦躁或其他明显不适，请马上告诉护士。"
        ),
        "risk": "high_risk",
    },
    {
        "code": "diabetes",
        "name": "糖尿病住院期间安全宣教",
        "original": (
            "糖尿病患者住院期间应按医护安排监测血糖、用药和进餐，不得自行增减胰岛素"
            "或降糖药。出现心慌、手抖、出汗、明显饥饿、头晕、乏力或意识改变时，"
            "可能为低血糖，应立即告知医护人员；出现持续口渴、多尿、恶心呕吐、"
            "呼吸异常或意识改变时也应及时求助。"
        ),
        "patient": (
            "请按护士安排测血糖、吃饭和用药，不要自己增减胰岛素或降糖药。"
            "如果出现心慌、手抖、出汗、很饿、头晕，或持续口渴、恶心呕吐，"
            "请立即呼叫护士。"
        ),
        "voice": (
            "住院期间请按安排测血糖、吃饭和用药，不要自行调整降糖药。"
            "如果出现心慌、手抖、出汗、很饿、头晕，或者持续口渴、恶心呕吐，"
            "请马上呼叫护士。"
        ),
        "risk": "high_risk",
    },
    {
        "code": "allergy",
        "name": "药物过敏安全宣教",
        "original": (
            "已知或疑似药物过敏者，应向每次接诊的医生、护士和药师主动说明具体药物名称"
            "及既往反应。不得自行再次试用可疑药物。用药后如出现全身皮疹、面唇舌肿胀、"
            "喉头发紧、呼吸困难、胸闷、头晕或意识改变，应立即停止自行活动并呼叫医护人员。"
        ),
        "patient": (
            "以后每次看病、检查或用药前，请主动告诉医生和护士您对什么药过敏、"
            "当时出现过什么反应，不要自行再试这种药。若用药后出现呼吸困难、"
            "喉咙发紧、脸或嘴唇肿、全身皮疹，请立即呼叫医护人员。"
        ),
        "voice": (
            "请记住，以后每次就医和用药前，都要主动告诉医生和护士具体对什么药过敏，"
            "以及当时出现过什么反应。若用药后出现呼吸困难、喉咙发紧、脸或嘴唇肿，"
            "请立即呼叫医护人员。"
        ),
        "risk": "high_risk",
    },
]


def upgrade() -> None:
    """创建宣教配置表并导入四类现有材料。"""
    op.create_table(
        "education_program",
        sa.Column("program_code", sa.String(length=64), nullable=False),
        sa.Column("program_name", sa.String(length=128), nullable=False),
        sa.Column("education_stage", sa.String(length=32), nullable=False),
        sa.Column("program_type", sa.String(length=32), nullable=False),
        sa.Column(
            "applicable_department",
            sa.String(length=256),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "applicable_disease_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "source_file",
            sa.String(length=512),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        *_business_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_code"),
    )
    op.create_index(
        "idx_education_program_status",
        "education_program",
        ["status", "deleted"],
        unique=False,
    )

    op.create_table(
        "education_program_version",
        sa.Column("program_id", sa.BigInteger(), nullable=False),
        sa.Column("version_code", sa.String(length=64), nullable=False),
        sa.Column(
            "publish_status",
            sa.String(length=32),
            server_default=sa.text("'published'"),
            nullable=False,
        ),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expire_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "content_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=128),
            server_default=sa.text("''"),
            nullable=False,
        ),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["education_program.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "program_id",
            "version_code",
            name="uq_education_version_code",
        ),
    )
    op.create_index(
        "idx_education_version_program",
        "education_program_version",
        ["program_id", "deleted"],
        unique=False,
    )

    op.create_table(
        "education_unit",
        sa.Column("program_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "parent_unit_id",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("unit_code", sa.String(length=64), nullable=False),
        sa.Column("unit_title", sa.String(length=128), nullable=False),
        sa.Column(
            "unit_type",
            sa.String(length=64),
            server_default=sa.text("'risk_warning'"),
            nullable=False,
        ),
        sa.Column("original_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("patient_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("voice_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("mandatory", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "teachback_required",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "risk_level",
            sa.String(length=32),
            server_default=sa.text("'important'"),
            nullable=False,
        ),
        sa.Column("sort_no", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_business_columns(),
        sa.ForeignKeyConstraint(
            ["program_version_id"],
            ["education_program_version.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "program_version_id",
            "unit_code",
            name="uq_education_unit_code",
        ),
    )
    op.create_index(
        "idx_education_unit_version",
        "education_unit",
        ["program_version_id", "sort_no"],
        unique=False,
    )

    bind = op.get_bind()
    for material in _MATERIALS:
        program_id = bind.execute(
            sa.text(
                """
                INSERT INTO education_program (
                    program_code, program_name, education_stage, program_type,
                    status, creator, updator
                ) VALUES (
                    :code, :name, 'in_hospital', 'nursing_safety',
                    'active', 'migration', 'migration'
                ) RETURNING id
                """
            ),
            material,
        ).scalar_one()
        snapshot = {
            "source_name": f"{material['name']}（系统内置版）",
            "requires_acknowledgement": True,
            "auto_play": True,
        }
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        version_id = bind.execute(
            sa.text(
                """
                INSERT INTO education_program_version (
                    program_id, version_code, publish_status, content_snapshot,
                    content_hash, creator, updator
                ) VALUES (
                    :program_id, '1.0', 'published',
                    CAST(:snapshot AS jsonb), :content_hash,
                    'migration', 'migration'
                ) RETURNING id
                """
            ),
            {
                "program_id": program_id,
                "snapshot": canonical,
                "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            },
        ).scalar_one()
        bind.execute(
            sa.text(
                """
                INSERT INTO education_unit (
                    program_version_id, unit_code, unit_title, unit_type,
                    original_text, patient_text, voice_text, mandatory,
                    teachback_required, risk_level, sort_no, creator, updator
                ) VALUES (
                    :version_id, :unit_code, :name, 'risk_warning',
                    :original, :patient, :voice, 1, 0, :risk, 1,
                    'migration', 'migration'
                )
                """
            ),
            {
                **material,
                "version_id": version_id,
                "unit_code": f"{material['code']}_main",
            },
        )


def downgrade() -> None:
    """删除 Demo 宣教配置表。"""
    op.drop_index("idx_education_unit_version", table_name="education_unit")
    op.drop_table("education_unit")
    op.drop_index(
        "idx_education_version_program",
        table_name="education_program_version",
    )
    op.drop_table("education_program_version")
    op.drop_index("idx_education_program_status", table_name="education_program")
    op.drop_table("education_program")
