"""Lakebase migration: grant schema permissions to the app service principal and run Alembic.

Connects as the developer (workspace CLI auth), resolves the Databricks App's
service principal, grants it CREATE/USAGE on the public schema, then runs
Alembic migrations so tables are owned by the developer identity.

Usage:
    uv run --directory app python ../scripts/migrate.py [OPTIONS]

Options:
    --app-name NAME       Databricks App name (default: usage-limits)
    --instance NAME       Lakebase instance name (default: usage-limits)
    --sp-username USER    Override SP Postgres username (skips auto-detection)
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg
from databricks.sdk import WorkspaceClient
from sqlalchemy import Engine, create_engine, event


def _resolve_sp_username(ws: WorkspaceClient, app_name: str) -> str:
    """Resolve the Postgres username for the app's service principal."""
    print(f"  Resolving service principal for app '{app_name}'...")
    app = ws.apps.get(app_name)
    sp_id = app.service_principal_id
    if not sp_id:
        raise RuntimeError(
            f"App '{app_name}' has no service_principal_id. "
            "Pass --sp-username manually."
        )
    sp = ws.service_principals.get(sp_id)
    username = sp.application_id
    if not username:
        raise RuntimeError(
            f"Service principal {sp_id} has no application_id. "
            "Pass --sp-username manually."
        )
    print(f"  SP application_id (Postgres username): {username}")
    return username


def _connect(ws: WorkspaceClient, instance_name: str) -> psycopg.Connection:
    """Connect to Lakebase as the developer identity."""
    print(f"  Resolving Lakebase instance '{instance_name}'...")
    instance = ws.database.get_database_instance(instance_name)
    host = instance.read_write_dns
    print(f"  Host: {host}")

    print("  Generating database credential...")
    cred = ws.database.generate_database_credential(instance_names=[instance_name])

    me = ws.current_user.me()
    username = me.user_name
    print(f"  Connecting as: {username}")

    conn = psycopg.connect(
        host=host,
        port=5432,
        user=username,
        password=cred.token,
        dbname="databricks_postgres",
        sslmode="require",
        autocommit=True,
    )
    return conn


def _grant_permissions(conn: psycopg.Connection, sp_username: str) -> None:
    """Grant schema-level permissions to the service principal."""
    print(f"  Granting permissions to '{sp_username}'...")

    ident = psycopg.sql.Identifier(sp_username)

    statements = [
        psycopg.sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ident),
        psycopg.sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(ident),
        psycopg.sql.SQL(
            "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {}"
        ).format(ident),
        psycopg.sql.SQL(
            "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {}"
        ).format(ident),
        psycopg.sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT ALL PRIVILEGES ON TABLES TO {}"
        ).format(ident),
        psycopg.sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT ALL PRIVILEGES ON SEQUENCES TO {}"
        ).format(ident),
    ]

    for stmt in statements:
        conn.execute(stmt)
        print(f"    OK: {stmt.as_string(conn)}")


def _run_alembic(engine: Engine) -> None:
    """Run Alembic migrations as the developer (table owner)."""
    from alembic import command
    from alembic.config import Config

    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    alembic_cfg = Config(os.path.join(app_dir, "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", os.path.join(os.path.abspath(app_dir), "alembic")
    )
    with engine.connect() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
    print("  Alembic migrations applied.")


def _create_tables(ws: WorkspaceClient, instance_name: str) -> None:
    """Run Alembic migrations as the developer (owner) identity."""
    print("  Running Alembic migrations...")

    instance = ws.database.get_database_instance(instance_name)
    host = instance.read_write_dns
    me = ws.current_user.me()
    username = me.user_name

    url = f"postgresql+psycopg://{username}:@{host}:5432/databricks_postgres"
    engine = create_engine(
        url,
        connect_args={"sslmode": "require"},
    )

    @event.listens_for(engine, "do_connect")
    def _refresh(dialect, conn_rec, cargs, cparams):
        cred = ws.database.generate_database_credential(
            instance_names=[instance_name]
        )
        cparams["password"] = cred.token

    _run_alembic(engine)
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lakebase migration: grant SP permissions + create tables"
    )
    parser.add_argument(
        "--app-name", default="usage-limits", help="Databricks App name (default: usage-limits)"
    )
    parser.add_argument(
        "--instance", default="usage-limits", help="Lakebase instance name (default: usage-limits)"
    )
    parser.add_argument(
        "--sp-username",
        default=None,
        help="Override SP Postgres username (skips auto-detection)",
    )
    args = parser.parse_args()

    print("=== Lakebase Migration ===")
    ws = WorkspaceClient()

    # 1. Resolve SP username
    sp_username = args.sp_username
    if not sp_username:
        sp_username = _resolve_sp_username(ws, args.app_name)

    # 2. Connect as developer
    conn = _connect(ws, args.instance)

    # 3. Grant permissions
    try:
        _grant_permissions(conn, sp_username)
    finally:
        conn.close()

    # 4. Create tables as owner
    _create_tables(ws, args.instance)

    print("=== Migration complete ===")


if __name__ == "__main__":
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
    sys.path.insert(0, os.path.abspath(app_dir))
    main()
