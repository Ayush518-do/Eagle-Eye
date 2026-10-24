"""Database engine and session handling (SQLAlchemy 2, SQLite by default).

Routes get a session through `get_db`. The session factory is its own dependency
(`get_session_factory`) so tests can point it at a temporary database, and so a background
task can open its own session from the same factory instead of reusing the request's.
"""
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import Settings, get_settings


def make_engine(database_url: str, *, foreign_keys: bool = True) -> Engine:
    """`foreign_keys=False` is for migrations only (see alembic/env.py); the app keeps the default."""
    kwargs = {}
    if database_url.startswith("sqlite"):
        # Requests and background tasks run in different threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record) -> None:
            # SQLite ignores foreign keys unless asked on every connection.
            cursor = dbapi_connection.cursor()
            cursor.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
            cursor.close()

    return engine


@lru_cache
def _session_factory_for(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(database_url), expire_on_commit=False)


def get_session_factory(settings: Settings = Depends(get_settings)) -> sessionmaker[Session]:
    return _session_factory_for(settings.database_url)


def get_db(factory: sessionmaker[Session] = Depends(get_session_factory)) -> Iterator[Session]:
    """One session per request. Routes commit explicitly; anything uncommitted is rolled back."""
    with factory() as session:
        yield session
