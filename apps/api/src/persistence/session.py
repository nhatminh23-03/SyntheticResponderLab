from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import AppSettings, get_settings


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, **_engine_kwargs(settings.database_url))


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True, class_=Session)


def create_session_factory(settings: AppSettings):
    engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)

