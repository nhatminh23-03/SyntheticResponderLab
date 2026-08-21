"""Resolve which database migrations should be applied to.

Alembic and the application have to agree on this, and until now they did not. ``alembic/env.py`` read
``os.getenv("DATABASE_URL")`` and nothing else, while ``AppSettings`` loads ``apps/api/.env``. With the
URL set only in that file -- the documented local setup -- alembic fell through to ``alembic.ini``'s
``sqlite:///./local-dev.db``, reported success, and built all nine tables in a database the application
never opens.

Nothing about that looks like a failure while it is happening, which is what makes it worth a module of
its own rather than another line in ``env.py``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

ALEMBIC_INI_DEFAULT = "sqlite:///./local-dev.db"


def _default_settings_factory() -> Any:
    # Imported lazily so this module stays usable from alembic's environment, which is loaded before
    # the application package is necessarily importable.
    from src.config.settings import AppSettings

    return AppSettings()


def resolve_migration_database_url(
    settings_factory: Optional[Callable[[], Any]] = None,
) -> str:
    """Return the database URL the application itself would open.

    An exported ``DATABASE_URL`` wins, because that is what production supplies. Otherwise the value
    comes from the same settings object the application uses, so ``.env`` is honoured. If neither
    provides one, this raises rather than letting alembic quietly migrate ``alembic.ini``'s default.
    """
    exported = (os.environ.get("DATABASE_URL") or "").strip()
    if exported:
        return exported

    factory = settings_factory or _default_settings_factory
    try:
        database_url = str(getattr(factory(), "database_url", "") or "").strip()
    except Exception as exc:  # noqa: BLE001 - any settings failure means we cannot know the target
        raise RuntimeError(
            "DATABASE_URL is not set and apps/api/.env does not provide one. Refusing to run "
            f"migrations against alembic.ini's default ({ALEMBIC_INI_DEFAULT}), which would build a "
            "second database the application never opens and report success."
        ) from exc

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL resolved to an empty value. Refusing to run migrations against "
            f"alembic.ini's default ({ALEMBIC_INI_DEFAULT})."
        )
    return database_url
