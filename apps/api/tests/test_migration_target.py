"""F-03: `alembic upgrade head` migrated a database the application never opens.

`alembic/env.py` read `os.getenv("DATABASE_URL")` and nothing else. `AppSettings` loads
`apps/api/.env`; alembic did not. With `DATABASE_URL` set only in that file -- the documented local
setup -- alembic fell through to `alembic.ini`'s `sqlalchemy.url = sqlite:///./local-dev.db`, reported
success, and created all nine tables in a second database while the application's own database stayed
empty.

Production masked it, because Render supplies a real environment variable.

The failure mode that matters is not the wrong path; it is that migrating the wrong database looks
exactly like migrating the right one.
"""

from __future__ import annotations

import pytest

from src.persistence.migration_target import resolve_migration_database_url


class _Settings:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url


def test_an_exported_variable_is_used_as_is(monkeypatch):
    """Production sets a real environment variable, and that must keep winning."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://host/prod")

    assert resolve_migration_database_url(settings_factory=lambda: _Settings("sqlite:///other.db")) == (
        "postgresql://host/prod"
    )


def test_the_env_file_is_used_when_nothing_is_exported(monkeypatch):
    """The documented local setup puts DATABASE_URL in apps/api/.env and exports nothing."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    resolved = resolve_migration_database_url(
        settings_factory=lambda: _Settings("sqlite:///./configured-by-dotenv.db")
    )

    assert resolved == "sqlite:///./configured-by-dotenv.db"


def test_alembic_ini_default_is_never_silently_used(monkeypatch):
    """With no configuration at all, refuse rather than migrate a database nobody asked for."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def _unconfigured():
        raise ValueError("DATABASE_URL field required")

    with pytest.raises(RuntimeError) as excinfo:
        resolve_migration_database_url(settings_factory=_unconfigured)

    message = str(excinfo.value)
    assert "DATABASE_URL" in message
    assert "local-dev.db" in message, "the message must name the trap it is refusing to fall into"


def test_an_empty_value_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "   ")

    assert resolve_migration_database_url(
        settings_factory=lambda: _Settings("sqlite:///./configured-by-dotenv.db")
    ) == "sqlite:///./configured-by-dotenv.db"


def test_migrations_and_the_app_resolve_the_same_database(test_settings, monkeypatch):
    """The whole point: whatever the application opens is what gets migrated."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert resolve_migration_database_url(settings_factory=lambda: test_settings) == (
        test_settings.database_url
    )
