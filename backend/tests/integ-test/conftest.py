"""PostgreSQL 集成测试夹具。"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

DEFAULT_TEST_DATABASE_URL = (
    "postgresql://medical:medical_dev_password@localhost:15432/medical_evaluate"
)


@pytest.fixture
def postgres_session_factory():
    """提供可提交但最终整体回滚的真实 PostgreSQL 会话工厂。"""
    database_url = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        connection = engine.connect()
        outer_transaction = connection.begin()
        connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL 测试环境不可用: {exc}")

    factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield factory
    finally:
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()
        engine.dispose()
