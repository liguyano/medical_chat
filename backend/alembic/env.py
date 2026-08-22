# 导入所有模型以支持autogenerate
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 导入统一模型包，确保批次 A 的全部模型注册到 Base.metadata。
from app.configs.app_config import get_app_config
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata
AUTOGENERATE_PLUGINS = [
    "alembic.autogenerate.*",
    "~alembic.autogenerate.comments",
]


def _resolve_database_url() -> str:
    """解析迁移连接串。

    生产默认仍从统一应用配置读取；当调用方显式覆写 Alembic 配置中的
    ``sqlalchemy.url``（例如临时测试库、发布流水线）时必须尊重该连接串，
    否则迁移会误跑到默认库而让调用方误以为目标库已升级。
    """
    configured = config.get_main_option("sqlalchemy.url")
    default_ini_url = (
        "postgresql://medical:medical_dev_password@localhost:15432/medical_evaluate"
    )
    if configured and configured != default_ini_url:
        return configured
    return get_app_config().database.url


config.set_main_option(
    "sqlalchemy.url",
    _resolve_database_url().replace("%", "%%"),
)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        autogenerate_plugins=AUTOGENERATE_PLUGINS,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Demo 项目不为纯注释差异生成迁移，结构、类型和约束仍参与检查。
            autogenerate_plugins=AUTOGENERATE_PLUGINS,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
