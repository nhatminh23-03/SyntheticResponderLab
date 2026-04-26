"""Add per-user usage counters for public-launch quota enforcement.

Revision ID: 0002_usage_counters
Revises: 0001_phase1_thin_slice
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_usage_counters"
down_revision = "0001_phase1_thin_slice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_usage_counters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Text(), nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=False),
        sa.Column("bucket_date_utc", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "metric_key",
            "bucket_date_utc",
            name="uq_user_usage_counters_owner_metric_bucket",
        ),
    )
    op.create_index(
        "ix_user_usage_counters_owner_bucket",
        "user_usage_counters",
        ["owner_user_id", "bucket_date_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_usage_counters_owner_bucket", table_name="user_usage_counters")
    op.drop_table("user_usage_counters")
