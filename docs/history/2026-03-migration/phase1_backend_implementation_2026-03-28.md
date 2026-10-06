# Phase 1 Thin Slice Backend Implementation

Updated: 2026-03-28  
Workspace root: `SyntheticResponderLab`  
Reference implementation kept untouched: `NeoSmart-Hackathon-App/`  
New implementation target: `apps/api/`  
Out of scope: frontend work, run execution, analysis pages, insights pages, interview flows

This document records what has been implemented so far for Phase 1 of the migration plan. It is the current backend baseline for the thin slice defined in `Documentation/phase0_thin_slice_backend_spec_2026-03-28.md`.

## 1. Scope Implemented

The Phase 1 backend foundation now supports these thin-slice capabilities:
- create study
- load study
- save study mode
- save audience
- save product
- product URL autofill
- product image analysis
- save market
- survey upload, parse, normalize, and validate
- workflow readiness
- persona preview

What did not change:
- no changes were made inside `NeoSmart-Hackathon-App/`
- no frontend or Next.js code was added
- no run execution, analysis, or interview APIs were implemented

## 2. New Backend Structure

The new backend lives in `apps/api/` and is organized as:

- `src/adapters/legacy_backend`
  - wraps existing Python logic from the legacy app
  - handles import-path bridging and temporary env injection for provider-backed legacy modules
- `src/services`
  - orchestration layer for studies, workflow readiness, and health checks
- `src/persistence`
  - SQLAlchemy models, session factory, and persistence helpers
- `src/api`
  - FastAPI app, routers, dependency wiring, and exception handling
- `src/schemas`
  - canonical request and response schemas, including canonical `Study`
- `alembic`
  - database migration config and initial schema migration
- `tests`
  - basic validation coverage for serializer, health, and study endpoints

Key files:
- `apps/api/pyproject.toml`
- `apps/api/src/api/app.py`
- `apps/api/src/api/studies.py`
- `apps/api/src/services/study_service.py`
- `apps/api/src/services/health_service.py`
- `apps/api/src/adapters/legacy_backend/domain.py`
- `apps/api/src/persistence/models.py`
- `apps/api/alembic/versions/0001_phase1_thin_slice.py`

## 3. Dependencies and Runtime Setup

Phase 1 added backend dependencies required by the spec:
- `fastapi`
- `uvicorn`
- `sqlalchemy`
- `alembic`
- `psycopg[binary]`
- `pydantic-settings`
- `python-multipart`
- `pandas`
- `pyarrow`
- `cryptography`
- `pytest`
- `httpx`

Implementation note:
- the local runtime available during implementation was Python `3.9.6`
- `apps/api/pyproject.toml` was made Python 3.9-compatible so the thin slice could actually run and be verified in this environment

## 4. Persistence Implemented

The Phase 1 SQLAlchemy model layer and initial Alembic migration now include:
- `studies`
- `study_section_states`
- `study_assets`
- `study_product_enrichments`
- `persona_preview_runs`
- `persona_preview_personas`
- `jobs`

Persistence behavior implemented:
- public-facing ids are generated separately from database UUID primary keys
- section state is stored as JSON payloads plus section status metadata
- survey uploads and product images are stored as assets with metadata and file references
- URL autofill and image analysis runs are persisted as enrichment records
- persona preview output is persisted both as a run record and row-level persona records
- study lifecycle status is recalculated from persisted section state and preview state

Alembic notes:
- `apps/api/alembic/env.py` now accepts `DATABASE_URL` from the environment
- the initial migration was adjusted to work on SQLite for local verification and still remain valid for a fuller DB target later

## 5. Canonical Study Model Implemented

The canonical API-facing study model from the Phase 0 spec is implemented in `apps/api/src/schemas/study.py` and serialized by `apps/api/src/services/study_service.py`.

It includes:
- root study metadata
- ownership fields
- section envelopes for `study_mode`, `audience`, `product`, `market`, and `survey`
- latest product enrichment summaries
- derived geography context
- workflow readiness
- latest persona preview result

Implementation details:
- all major setup sections are always returned as envelopes, even when not yet saved
- `survey` includes parsed schema, question count, source asset metadata, and parse warnings
- workflow readiness is returned inside the canonical study for frontend convenience
- persona preview response includes request metadata, warnings, prior notes, and persona rows

## 6. Legacy Adapters Implemented

Phase 1 intentionally preserves legacy Python logic rather than rewriting it.

The adapter layer wraps these legacy capabilities:
- `AudienceFilter`
- `BusinessProductContext`
- `MarketContext`
- survey parser, normalizer, and validator
- geography context lookup
- persona preview generation
- product URL autofill
- product image analysis

Adapter behavior:
- the new backend injects the legacy app path at runtime rather than copying legacy modules
- provider-backed legacy code that still reads raw env vars is wrapped with temporary env injection
- the service layer replaces Streamlit session state with database-backed study persistence
- fallback behavior from the legacy app is preserved where possible

Important files:
- `apps/api/src/adapters/legacy_backend/runtime.py`
- `apps/api/src/adapters/legacy_backend/domain.py`

## 7. API Endpoints Implemented

The following Phase 1 routes are implemented in `apps/api/src/api/studies.py` and `apps/api/src/api/health.py`:

- `GET /api/v1/health`
- `POST /api/v1/studies`
- `GET /api/v1/studies/{study_id}`
- `PATCH /api/v1/studies/{study_id}/study-mode`
- `PATCH /api/v1/studies/{study_id}/audience`
- `PATCH /api/v1/studies/{study_id}/product`
- `POST /api/v1/studies/{study_id}/product/url-autofill`
- `POST /api/v1/studies/{study_id}/product/image-analysis`
- `PATCH /api/v1/studies/{study_id}/market`
- `POST /api/v1/studies/{study_id}/survey/upload`
- `GET /api/v1/studies/{study_id}/workflow`
- `POST /api/v1/studies/{study_id}/personas/preview`

`/api/v1/health` behavior:
- hard-fail checks: database, artifacts root, legacy app root, Python dependencies
- degraded checks: OpenRouter, Google Vision, grounding priors, HUD lookups
- app startup now fails if hard-fail checks fail

## 8. Verification Completed

Verification performed during implementation:

- Python syntax validation across `src`, `tests`, and `alembic`
- dependency install into `apps/api/.venv`
- Alembic upgrade against a fresh SQLite verification database
- automated tests via `pytest`

Verified results:
- Alembic migration applied successfully
- tests passing: `5 passed`

Current test coverage includes:
- canonical serializer behavior
- health endpoint failure envelope behavior
- study creation
- study mode patching
- audience save plus workflow readiness retrieval

## 9. Generated Local Artifacts

Local development artifacts created during implementation:
- `apps/api/.venv/`
- `apps/api/local-dev.db`
- `apps/api/phase1-verify.db`
- `apps/api/.pytest_cache/`

These are implementation-time verification artifacts, not product deliverables.

## 10. Known Constraints and Gaps

The Phase 1 thin slice is working, but these runtime dependencies still matter:

- `ARTIFACTS_ROOT` must exist and be writable
- `LEGACY_APP_ROOT` must point to `NeoSmart-Hackathon-App/`
- `OPENROUTER_API_KEY` is needed for live product URL autofill behavior
- `GOOGLE_CLOUD_API_KEY` or Google service-account credentials are needed for image analysis
- `HUD_API_TOKEN` is optional, but without it missing HUD lookup files degrade geography support
- missing grounding priors or lookup parquet files in the legacy data directories will degrade persona preview rather than hard-fail it

Phase 1 also still has intentional limitations:
- no auth or tenancy enforcement yet beyond stored owner fields
- no background job workers yet
- no async run orchestration yet
- no frontend contract tests yet
- no Postgres-specific verification yet in this environment

## 11. Recommended Next Step

The next implementation step should be Phase 2 API hardening, not more legacy rewiring.

Recommended focus:
- add stronger endpoint test coverage for product, survey upload, URL autofill, image analysis, and persona preview
- validate the migration and models against Postgres, not only SQLite
- add `.env.example` and startup documentation for the new backend
- define response fixtures that the future Next.js frontend can build against
- begin the first frontend vertical slice only after the backend contract is stable enough to avoid churn

## 12. Summary

Phase 1 successfully established the thin-slice Python backend foundation under `apps/api/` while preserving the legacy application as the source of truth. The backend now has a real API surface, canonical study serialization, persistence, legacy adapters, health checks, migrations, and basic tests. This is a solid base for Phase 2 hardening and for the eventual premium Next.js frontend to consume.
