"""数据库基础配置
作用：定义SQLAlchemy Base类和数据库会话
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLAlchemy Base类
Base = declarative_base()

# 数据库引擎（将在配置加载后初始化）
engine = None
SessionLocal = None


def init_db(database_url: str):
    """初始化数据库引擎和会话
    作用：根据配置创建数据库引擎和会话工厂
    Args:
        - database_url: 数据库连接字符串
    """
    global engine, SessionLocal
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """获取数据库会话
    作用：FastAPI依赖注入使用的数据库会话生成器
    Return:
        - db: 数据库会话对象
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
