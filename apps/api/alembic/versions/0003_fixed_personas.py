"""Add and seed the fixed interview personas from personas-B.csv.

Revision ID: 0003_fixed_personas
Revises: 0002_usage_counters
Create Date: 2026-09-04
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

from src.persistence.persona_seed import load_persona_seed_rows


revision = "0003_fixed_personas"
down_revision = "0002_usage_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personas",
        sa.Column("persona_id", sa.Text(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("persona_id"),
        sa.UniqueConstraint("row_index"),
    )

    personas_table = sa.table(
        "personas",
        sa.column("persona_id", sa.Text()),
        sa.column("row_index", sa.Integer()),
        sa.column("profile_json", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    created_at = datetime(2026, 9, 4, tzinfo=timezone.utc)
    op.bulk_insert(
        personas_table,
        [dict(seed_row, created_at=created_at) for seed_row in load_persona_seed_rows()],
    )


def downgrade() -> None:
    op.drop_table("personas")
