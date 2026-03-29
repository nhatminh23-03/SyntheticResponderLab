"""Initial thin-slice backend schema.

Revision ID: 0001_phase1_thin_slice
Revises:
Create Date: 2026-03-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_phase1_thin_slice"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Text(), nullable=True),
        sa.Column("owner_org_id", sa.Text(), nullable=True),
        sa.Column("study_mode", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.Text(), nullable=False),
        sa.Column("latest_persona_preview_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_studies_owner_user_id", "studies", ["owner_user_id"])
    op.create_index("ix_studies_lifecycle_status", "studies", ["lifecycle_status"])

    op.create_table(
        "study_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("storage_provider", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_study_assets_study_id", "study_assets", ["study_id"])

    op.create_table(
        "study_section_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("validation_errors_json", sa.JSON(), nullable=True),
        sa.Column("source_asset_id", sa.Uuid(), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_asset_id"], ["study_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_id", "section_key", name="uq_study_section_states_study_id_section_key"),
    )

    op.create_table(
        "study_product_enrichments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("enrichment_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_url", sa.Text(), nullable=True),
        sa.Column("source_asset_id", sa.Uuid(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("applied_to_product", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_asset_id"], ["study_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )

    op.create_table(
        "persona_preview_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("use_grounded_priors", sa.Boolean(), nullable=False),
        sa.Column("use_geography_filtered_priors", sa.Boolean(), nullable=False),
        sa.Column("use_cex_affordability_priors", sa.Boolean(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("generation_mode", sa.Text(), nullable=True),
        sa.Column("grounded_priors_available", sa.Boolean(), nullable=True),
        sa.Column("cex_affordability_available", sa.Boolean(), nullable=True),
        sa.Column("geography_context_json", sa.JSON(), nullable=True),
        sa.Column("prior_notes_json", sa.JSON(), nullable=False),
        sa.Column("warning_messages_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )

    op.create_table(
        "persona_preview_personas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("preview_run_id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=False),
        sa.Column("fit_tier", sa.Text(), nullable=True),
        sa.Column("segment_label", sa.Text(), nullable=True),
        sa.Column("persona_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["preview_run_id"], ["persona_preview_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preview_run_id", "row_index", name="uq_persona_preview_personas_preview_run_id_row_index"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["study_id"], ["studies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("studies", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_studies_latest_persona_preview_run_id",
                "persona_preview_runs",
                ["latest_persona_preview_run_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            "fk_studies_latest_persona_preview_run_id",
            "studies",
            "persona_preview_runs",
            ["latest_persona_preview_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("studies", schema=None) as batch_op:
            batch_op.drop_constraint("fk_studies_latest_persona_preview_run_id", type_="foreignkey")
    else:
        op.drop_constraint("fk_studies_latest_persona_preview_run_id", "studies", type_="foreignkey")
    op.drop_table("jobs")
    op.drop_table("persona_preview_personas")
    op.drop_table("persona_preview_runs")
    op.drop_table("study_product_enrichments")
    op.drop_table("study_section_states")
    op.drop_index("ix_study_assets_study_id", table_name="study_assets")
    op.drop_table("study_assets")
    op.drop_index("ix_studies_lifecycle_status", table_name="studies")
    op.drop_index("ix_studies_owner_user_id", table_name="studies")
    op.drop_table("studies")
