from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.persistence.base import Base
from src.persistence import models  # noqa: F401
from src.persistence.migration_target import resolve_migration_database_url


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolved the same way the application resolves it, so migrations cannot be applied to a database the
# app never opens. Reading os.getenv alone meant a URL set only in apps/api/.env -- the documented local
# setup -- fell through to alembic.ini's default and migrated a second database, reporting success.
config.set_main_option("sqlalchemy.url", resolve_migration_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
