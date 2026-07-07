"""Database engine and session setup.

Works on SQLite (dev) and PostgreSQL (prod) via the same SQLAlchemy models.
JSON columns use the generic SQLAlchemy ``JSON`` type so both backends work.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    # Needed because FastAPI may touch the session across threads.
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

if settings.database_url.startswith("sqlite"):
    # WAL allows the ingestion process to write while the API server reads.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Import models first so metadata is populated."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Lightweight additive migrations for the dev SQLite DB (create_all won't ALTER
    existing tables). Adds columns introduced after a table was first created."""
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        conv_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(conversations)"))}
        if "kind" not in conv_cols:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN kind VARCHAR DEFAULT 'chat'"))
        if "campaign_id" not in conv_cols:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN campaign_id INTEGER"))
        camp_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(campaigns)"))}
        if "type" not in camp_cols:
            conn.execute(text("ALTER TABLE campaigns ADD COLUMN type VARCHAR DEFAULT 'external'"))
        # Per-account data isolation: every existing row belonged to the admin (the only prior user),
        # so backfill owner='admin'. source_files default NULL = the SHARED brand library.
        for tbl in ("conversations", "campaigns", "assets", "opportunities", "calendar_tasks"):
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({tbl})"))}
            if "owner" not in cols:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN owner VARCHAR DEFAULT 'admin'"))
        sf_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(source_files)"))}
        if "owner" not in sf_cols:
            conn.execute(text("ALTER TABLE source_files ADD COLUMN owner VARCHAR"))
        # Per-photo vision tags (attire/expression/…) so a feature picks the shot that fits the request.
        emp_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(employees)"))}
        if emp_cols and "photo_analysis" not in emp_cols:
            conn.execute(text("ALTER TABLE employees ADD COLUMN photo_analysis JSON"))
        ep_info = list(conn.execute(text("PRAGMA table_info(employee_photos)")))
        if ep_info and "analysis" not in {row[1] for row in ep_info}:
            conn.execute(text("ALTER TABLE employee_photos ADD COLUMN analysis JSON"))
