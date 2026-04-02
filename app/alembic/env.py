"""Alembic env — reuses create_engine_from_config() for both env-var and Lakebase modes."""
from __future__ import annotations

from alembic import context

from core.models import Base
import core.models as _models  # noqa: F401 — register all tables

target_metadata = Base.metadata


def run_migrations_online() -> None:
    """Run migrations against a live database connection.

    If a connection was injected via config attributes (startup path),
    use it directly. Otherwise build a fresh engine (CLI path).
    """
    connectable = context.config.attributes.get("connection")

    if connectable is not None:
        _run_with_connection(connectable)
    else:
        from core.config import AppConfig
        from core.db import create_engine_from_config

        config = AppConfig.from_env()
        engine = create_engine_from_config(config)
        with engine.connect() as connection:
            _run_with_connection(connection)
        engine.dispose()


def _run_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
