"""Alembic 初始迁移临时数据库集成测试。"""
import os
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from alembic import command

DEFAULT_DATABASE_URL = (
    "postgresql://medical:medical_dev_password@localhost:15432/medical_evaluate"
)
EXPECTED_REVISION = "20260822_patient_portal"
EXPECTED_TABLE_COUNT = 49
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_initial_migration_upgrade_and_downgrade():
    """初始迁移应能在独立临时数据库完整升级和回滚。"""
    source_url = make_url(os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL))
    database_name = f"medical_evaluate_test_{uuid4().hex}"
    admin_url = source_url.set(database="postgres")
    test_url = source_url.set(database=database_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    try:
        alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
        alembic_config.set_main_option(
            "script_location",
            str(BACKEND_ROOT / "alembic"),
        )
        alembic_config.set_main_option(
            "sqlalchemy.url",
            test_url.render_as_string(hide_password=False),
        )

        command.upgrade(alembic_config, "head")

        test_engine = create_engine(test_url)
        try:
            table_names = set(inspect(test_engine).get_table_names())
            assert "alembic_version" in table_names
            assert len(table_names - {"alembic_version"}) == EXPECTED_TABLE_COUNT
            inspector = inspect(test_engine)
            patient_columns = {
                column["name"] for column in inspector.get_columns("patient")
            }
            encounter_columns = {
                column["name"]
                for column in inspector.get_columns("patient_encounter")
            }
            event_columns = {
                column["name"]
                for column in inspector.get_columns("interaction_event")
            }
            assert {
                "emergency_contact_name",
                "emergency_contact_relation",
                "emergency_contact_phone",
                "address",
            } <= patient_columns
            assert {
                "admission_source",
                "nursing_level",
                "insurance_type",
                "allergy_summary",
            } <= encounter_columns
            assert "source_invocation_id" in event_columns
            with test_engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == EXPECTED_REVISION
        finally:
            test_engine.dispose()

            command.check(alembic_config)
            # 患者门户迁移本身必须可回滚；更早的历史类型清理迁移明确不可逆，
            # 因此不把测试数据库一路降到 base。
            command.downgrade(alembic_config, "20260822_task_preparation")

            downgraded_engine = create_engine(test_url)
            try:
                remaining = set(inspect(downgraded_engine).get_table_names())
                assert len(remaining - {"alembic_version"}) == 33
                with downgraded_engine.connect() as connection:
                    revision = connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                assert revision == "20260822_task_preparation"
            finally:
                downgraded_engine.dispose()
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()
