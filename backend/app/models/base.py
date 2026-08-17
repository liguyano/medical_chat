"""数据库模型基础设施
作用：定义 SQLAlchemy 2.0 声明基类、统一业务字段和数据库会话。
"""

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""


class BusinessBaseMixin:
    """业务表统一字段
    作用：落实《数据库表业务设计.md》§4 的统一字段规范。
    """

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    creator: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="创建人账号或系统标识"
    )
    updator: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="最后更新人账号或系统标识"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        comment="创建时间",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
        comment="更新时间",
    )
    deleted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="逻辑删除：0未删除，1已删除",
    )


engine = None
SessionLocal: sessionmaker[Session] | None = None


def init_db(
    database_url: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    echo: bool = False,
) -> None:
    """初始化数据库引擎和会话工厂
    Args:
        - database_url: PostgreSQL 连接字符串
        - pool_size: 连接池常驻连接数
        - max_overflow: 连接池额外连接数
        - pool_pre_ping: 借出连接前是否检查可用性
        - echo: 是否输出 SQL 日志
    """
    global engine, SessionLocal
    resolved_url = database_url.replace(
        "@localhost:",
        "@127.0.0.1:",
    )
    engine = create_engine(
        resolved_url,
        pool_pre_ping=pool_pre_ping,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
    )
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话
    作用：提供 FastAPI 依赖注入使用的数据库会话生成器。
    Return:
        - db: SQLAlchemy Session
    """
    if SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
