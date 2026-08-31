"""Database engine, session handling and schema creation."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base

_settings = get_settings()

if _settings.database_url.startswith("sqlite:///"):
    db_path = Path(_settings.database_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover
    """Enable FK enforcement + WAL. SQLite disables foreign keys by default."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
    except Exception:
        pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def rebuild_schema(target=None) -> None:
    """Drop every table the models declare, then recreate them.

    `create_all` adds MISSING tables and never alters an existing one, so a
    database written before a column existed stays broken however many times it
    is reseeded -- `--force` wiped the rows and the next INSERT still failed on
    `table ... has no column named rate_provenance`. D24 migrates by reseed, so
    reseeding has to actually rebuild the schema and not just empty it.

    DESTRUCTIVE by design: this is the demo database, disposable by D13, and the
    only caller is an explicit `--force`.
    """
    bind = target if target is not None else engine
    Base.metadata.drop_all(bind=bind)
    Base.metadata.create_all(bind=bind)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
