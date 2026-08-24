"""Add fixed persona sets: a reviewer-frozen selection of preview personas.

Revision ID: 0003_fixed_persona_sets
Revises: 0002_usage_counters
Create Date: 2026-08-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_fixed_persona_sets"
down_revision = "0002_usage_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fixed_persona_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("preview_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("generation_mode", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_fixed_persona_sets_public_id"),
        sa.UniqueConstraint("study_id", name="uq_fixed_persona_sets_study_id"),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preview_run_id"], ["persona_preview_runs.id"]),
    )
    op.create_index("ix_fixed_persona_sets_study_id", "fixed_persona_sets", ["study_id"])
    op.create_table(
        "fixed_persona_set_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("preview_persona_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("set_id", "preview_persona_id", name="uq_fixed_persona_set_members_set_persona"),
        sa.ForeignKeyConstraint(["set_id"], ["fixed_persona_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preview_persona_id"], ["persona_preview_personas.id"]),
    )
    op.create_index("ix_fixed_persona_set_members_set_id", "fixed_persona_set_members", ["set_id"])


def downgrade() -> None:
    op.drop_index("ix_fixed_persona_set_members_set_id", table_name="fixed_persona_set_members")
    op.drop_table("fixed_persona_set_members")
    op.drop_index("ix_fixed_persona_sets_study_id", table_name="fixed_persona_sets")
    op.drop_table("fixed_persona_sets")
