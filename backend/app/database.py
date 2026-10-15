from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)
    # Lightweight SQLite schema migration for existing prototype databases.
    if _is_sqlite:
        with engine.begin() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(monitors)").fetchall()}
            for name, sql in [
                ("sensitivity", "INTEGER NOT NULL DEFAULT 2"),
                ("notify_email", "BOOLEAN NOT NULL DEFAULT 0"),
                ("notify_telegram", "BOOLEAN NOT NULL DEFAULT 0"),
            ]:
                if name not in columns:
                    conn.exec_driver_sql(f"ALTER TABLE monitors ADD COLUMN {name} {sql}")