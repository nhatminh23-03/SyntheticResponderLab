"""Persist interview transcript turns and provider-reported usage.

Revision ID: 0004_interview_turn
Revises: 0003_fixed_personas
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_interview_turn"
down_revision = "0003_fixed_personas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_turn",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("tokens_in", sa.BigInteger(), nullable=False),
        sa.Column("tokens_out", sa.BigInteger(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=24, scale=18), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cost_usd >= 0", name="ck_interview_turn_cost_usd_nonnegative"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_interview_turn_role"),
        sa.CheckConstraint("tokens_in >= 0", name="ck_interview_turn_tokens_in_nonnegative"),
        sa.CheckConstraint("tokens_out >= 0", name="ck_interview_turn_tokens_out_nonnegative"),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_turn_study_session_created",
        "interview_turn",
        ["study_id", "session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_turn_study_session_created",
        table_name="interview_turn",
    )
    op.drop_table("interview_turn")
