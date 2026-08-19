"""数据库引擎与会话。SQLite WAL 模式，短事务；推理调用不跨事务。

说明：M0 阶段用 Base.metadata.create_all() 建表；schema 首次变更时再引入
Alembic 迁移（脚手架已预留依赖）。
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy.exc import OperationalError

    from . import models  # noqa: F401  确保所有表已注册
    try:
        Base.metadata.create_all(engine)
    except OperationalError:
        # backend 与 worker 同时首次启动时可能并发建表，重试一次即可
        Base.metadata.create_all(engine)
