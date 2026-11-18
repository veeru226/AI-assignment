from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Always stores UTC and returns timezone-aware values (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Require an aware datetime and convert it to UTC (naive UTC on SQLite) for storage."""
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect):
        """Return the stored value as a timezone-aware UTC datetime."""
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def make_engine(database_url: str) -> Engine:
    """Create an engine, applying SQLite thread/timeout settings and WAL pragmas when relevant."""
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
    engine = create_engine(database_url, **kwargs)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            """Enable WAL, relaxed fsync and foreign-key enforcement on each new connection."""
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")  # readers don't block the click writer
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    """Return a sessionmaker bound to the engine with expire_on_commit and autoflush disabled."""
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
