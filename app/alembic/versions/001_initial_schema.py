"""Initial schema — all application tables.

Revision ID: 001
Revises: None
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budget_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("daily_dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("weekly_dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_custom", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id"),
        sa.CheckConstraint("entity_type IN ('user', 'group')", name="ck_entity_type"),
    )

    op.create_table(
        "default_budgets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("daily_dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("weekly_dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("monthly_dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "warnings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("dollar_usage", sa.Numeric(10, 2), nullable=True),
        sa.Column("dollar_limit", sa.Numeric(10, 2), nullable=True),
        sa.Column("enforced_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolved_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "reason"),
    )

    op.create_table(
        "usage_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("dollar_cost_1d", sa.Numeric(10, 2), nullable=True),
        sa.Column("dollar_cost_7d", sa.Numeric(10, 2), nullable=True),
        sa.Column("dollar_cost_30d", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_tokens_1d", sa.BigInteger(), nullable=True),
        sa.Column("total_tokens_7d", sa.BigInteger(), nullable=True),
        sa.Column("total_tokens_30d", sa.BigInteger(), nullable=True),
        sa.Column("request_count_1d", sa.Integer(), nullable=True),
        sa.Column("request_count_7d", sa.Integer(), nullable=True),
        sa.Column("request_count_30d", sa.Integer(), nullable=True),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "session_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("user_email", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_session_mappings_session_id", "session_mappings", ["session_id"])
    op.create_index("ix_session_mappings_user_email", "session_mappings", ["user_email"])

    op.create_table(
        "app_config",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_index("ix_session_mappings_user_email", table_name="session_mappings")
    op.drop_index("ix_session_mappings_session_id", table_name="session_mappings")
    op.drop_table("session_mappings")
    op.drop_table("audit_log")
    op.drop_table("usage_snapshots")
    op.drop_table("warnings")
    op.drop_table("default_budgets")
    op.drop_table("budget_configs")
