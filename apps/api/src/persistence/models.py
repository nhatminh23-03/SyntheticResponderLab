from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.persistence.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    owner_user_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_org_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    study_mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False)
    latest_persona_preview_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("persona_preview_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    section_states: Mapped[List["StudySectionState"]] = relationship(
        back_populates="study",
        cascade="all, delete-orphan",
        foreign_keys="StudySectionState.study_id",
    )
    assets: Mapped[List["StudyAsset"]] = relationship(back_populates="study", cascade="all, delete-orphan")
    enrichments: Mapped[List["StudyProductEnrichment"]] = relationship(back_populates="study", cascade="all, delete-orphan")
    persona_preview_runs: Mapped[List["PersonaPreviewRun"]] = relationship(
        back_populates="study",
        cascade="all, delete-orphan",
        foreign_keys="PersonaPreviewRun.study_id",
    )
    latest_persona_preview_run: Mapped[Optional["PersonaPreviewRun"]] = relationship(
        foreign_keys=[latest_persona_preview_run_id],
        post_update=True,
    )


class StudyAsset(Base):
    __tablename__ = "study_assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_provider: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    study: Mapped[Study] = relationship(back_populates="assets")


class StudySectionState(Base):
    __tablename__ = "study_section_states"
    __table_args__ = (UniqueConstraint("study_id", "section_key", name="uq_study_section_states_study_id_section_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    value_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    validation_errors_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    source_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("study_assets.id", ondelete="SET NULL"), nullable=True)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    study: Mapped[Study] = relationship(back_populates="section_states")
    source_asset: Mapped[Optional[StudyAsset]] = relationship()


class StudyProductEnrichment(Base):
    __tablename__ = "study_product_enrichments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    enrichment_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("study_assets.id", ondelete="SET NULL"), nullable=True)
    request_json: Mapped[Dict] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    error_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    applied_to_product: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    study: Mapped[Study] = relationship(back_populates="enrichments")
    source_asset: Mapped[Optional[StudyAsset]] = relationship()


class PersonaPreviewRun(Base):
    __tablename__ = "persona_preview_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    use_grounded_priors: Mapped[bool] = mapped_column(Boolean, nullable=False)
    use_geography_filtered_priors: Mapped[bool] = mapped_column(Boolean, nullable=False)
    use_cex_affordability_priors: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generation_mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grounded_priors_available: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    cex_affordability_available: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    geography_context_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    prior_notes_json: Mapped[List] = mapped_column(JSON, default=list, nullable=False)
    warning_messages_json: Mapped[List] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

    study: Mapped[Study] = relationship(back_populates="persona_preview_runs", foreign_keys=[study_id])
    personas: Mapped[List["PersonaPreviewPersona"]] = relationship(back_populates="preview_run", cascade="all, delete-orphan")


class PersonaPreviewPersona(Base):
    __tablename__ = "persona_preview_personas"
    __table_args__ = (UniqueConstraint("preview_run_id", "row_index", name="uq_persona_preview_personas_preview_run_id_row_index"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    preview_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persona_preview_runs.id", ondelete="CASCADE"), nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    persona_id: Mapped[str] = mapped_column(Text, nullable=False)
    fit_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    segment_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_json: Mapped[Dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    preview_run: Mapped[PersonaPreviewRun] = relationship(back_populates="personas")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("studies.id", ondelete="SET NULL"), nullable=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Dict] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    error_json: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class UserUsageCounter(Base):
    __tablename__ = "user_usage_counters"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "metric_key",
            "bucket_date_utc",
            name="uq_user_usage_counters_owner_metric_bucket",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    bucket_date_utc: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
