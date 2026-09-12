"""Add durable cached interview answers.

Revision ID: 0005_interview_cache
Revises: 0004_interview_turn
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_interview_cache"
down_revision = "0004_interview_turn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_cache",
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("prior_turn_hash", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("response_model", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key"),
    )


def downgrade() -> None:
    op.drop_table("interview_cache")
