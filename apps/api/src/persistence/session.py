from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import AppSettings, get_settings


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    return kwargs


def _apply_sqlite_pragmas(engine, database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
    _apply_sqlite_pragmas(engine, settings.database_url)
    return engine


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True, class_=Session)


def create_session_factory(settings: AppSettings):
    engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
    _apply_sqlite_pragmas(engine, settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)

