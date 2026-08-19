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
    cur.execute("PRAGMA busy_timeout=30000")  # 大批量导入时 API 写入需等 worker 的批提交
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


def _migrate_schema() -> None:
    """开发期轻量迁移：styles 表补 project_id 并改为 (project_id, name) 唯一。"""
    from sqlalchemy import text
    with engine.begin() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(styles)"))]
        if "project_id" in cols:
            return
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("""
            CREATE TABLE styles_new (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                name VARCHAR(200) NOT NULL,
                method VARCHAR(20) NOT NULL,
                notes TEXT,
                locked_split VARCHAR(10),
                created_at DATETIME,
                CONSTRAINT uq_style_project_name UNIQUE (project_id, name)
            )"""))
        conn.execute(text("""
            INSERT INTO styles_new (id, project_id, name, method, notes, locked_split, created_at)
            SELECT s.id,
                   (SELECT i.project_id FROM images i WHERE i.style_id = s.id LIMIT 1),
                   s.name, s.method, s.notes, s.locked_split, s.created_at
            FROM styles s"""))
        conn.execute(text("DROP TABLE styles"))
        conn.execute(text("ALTER TABLE styles_new RENAME TO styles"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_styles_project_id ON styles (project_id)"))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def init_db() -> None:
    from sqlalchemy.exc import OperationalError

    from . import models  # noqa: F401  确保所有表已注册
    try:
        Base.metadata.create_all(engine)
    except OperationalError:
        # backend 与 worker 同时首次启动时可能并发建表，重试一次即可
        Base.metadata.create_all(engine)
    _migrate_schema()
