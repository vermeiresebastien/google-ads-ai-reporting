from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from gads.config import get_settings
from gads.platforms import ensure_account_platform, ensure_proposed_actions_table

_engine = None
_session_factory = None


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def _is_sqlite_file(url: str) -> bool:
    return _is_sqlite_url(url) and ":memory:" not in url and "mode=memory" not in url


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict = {}
        if _is_sqlite_url(url):
            # timeout = seconds the pysqlite busy handler waits for locks
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, pool_pre_ping=True, **kwargs)

        @event.listens_for(_engine, "connect")
        def _sqlite_on_connect(dbapi_connection, _connection_record):
            if not _is_sqlite_url(url):
                return
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            if _is_sqlite_file(url):
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
        ensure_account_platform(_engine)
        ensure_proposed_actions_table(_engine)
        if _is_sqlite_file(url):
            # Apply WAL immediately on the bootstrap connection, not only on later connects.
            with _engine.begin() as connection:
                connection.execute(text("PRAGMA journal_mode=WAL"))
                connection.execute(text("PRAGMA busy_timeout=30000"))
    return _engine


def get_sessionmaker():
    get_engine()
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
