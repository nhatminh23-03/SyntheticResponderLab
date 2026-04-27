# Codebase Index

Date: 2026-04-13
Workspace: `SyntheticResponderLab`

## 1. What This Project Is

This repository is a migration from an older Python/Streamlit research prototype into a productized two-app stack:

- `apps/web`: a Next.js 14 one-page guided workflow UI
- `apps/api`: a FastAPI backend that persists study state and calls into legacy Python modules

The product flow is:

1. create or restore a study
2. save study mode
3. save audience, product, market, survey, and experiment setup
4. generate a persona preview
5. run a simulation
6. inspect analysis and executive insights

The new code does not reimplement the research engine in TypeScript. It treats the old Python backend as the source of truth for:

- schema validation
- survey parsing and normalization
- geography grounding
- persona generation
- response generation
- benchmark and realism logic
- rule-based findings and executive insights
- product URL and image enrichment

## 2. Current Repository Reality

The intended architecture is now runnable locally in this workspace.

Important implementation note:

- the original `NeoSmart-Hackathon-App/` submodule content was missing from this checkout
- a local compatibility legacy tree was added under `NeoSmart-Hackathon-App/` so the new API can boot and exercise the current product flow

The compatibility tree provides:

- `NeoSmart-Hackathon-App/backend/*`
- `NeoSmart-Hackathon-App/data/processed/priors`
- `NeoSmart-Hackathon-App/data/processed/lookups`
- `NeoSmart-Hackathon-App/data/processed/benchmarks`
- `NeoSmart-Hackathon-App/Provided Info/...`

This means the app is now installable and runnable, even though it is not the original full legacy prototype implementation.

## 3. Top-Level Map

- `README.md`
  - setup overview and intended stack
- `Documentation/`
  - migration plans and phased implementation notes
- `apps/api/`
  - FastAPI app, persistence layer, schemas, Alembic migration, tests
- `apps/web/`
  - Next.js app, workflow sections, providers, chart adapters, tests
- `UI Prototype/`
  - early visual reference artifacts
- `NeoSmart-Hackathon-App/`
  - supposed to contain the untouched legacy reference app, but currently empty

## 4. Backend Index

### 4.1 Backend purpose

`apps/api` owns canonical study state and API orchestration. It does not own the domain engine. It validates and persists inputs, then delegates domain work to legacy Python modules.

### 4.2 Main entrypoints

- `apps/api/src/main.py`
  - exports the FastAPI app
- `apps/api/src/api/app.py`
  - creates the app, CORS, lifespan checks, routers, request error handling
- `apps/api/src/api/studies.py`
  - all study-related endpoints
- `apps/api/src/api/health.py`
  - health endpoint

### 4.3 Core service layer

- `apps/api/src/services/study_service.py`
  - primary orchestration file
  - creates studies
  - saves each setup section
  - persists uploads and enrichments
  - generates persona previews
  - runs simulations and stability checks
  - builds analysis and insights views from saved run data
- `apps/api/src/services/workflow_service.py`
  - derives stage readiness for the one-page setup flow
- `apps/api/src/services/health_service.py`
  - startup and dependency checks

### 4.4 Persistence layer

- `apps/api/src/persistence/models.py`
  - SQLAlchemy models for:
    - `studies`
    - `study_section_states`
    - `study_assets`
    - `study_product_enrichments`
    - `persona_preview_runs`
    - `persona_preview_personas`
    - `jobs`
- `apps/api/src/persistence/session.py`
  - engine and session factory
- `apps/api/src/persistence/storage.py`
  - stores uploaded artifacts on the local filesystem under `ARTIFACTS_ROOT`
- `apps/api/alembic/versions/0001_phase1_thin_slice.py`
  - initial migration

### 4.5 Legacy adapter layer

- `apps/api/src/adapters/legacy_backend/runtime.py`
  - injects `LEGACY_APP_ROOT` into `sys.path`
  - temporarily sets env vars for legacy code
- `apps/api/src/adapters/legacy_backend/domain.py`
  - wrapper around legacy backend modules
  - validates audience/product/market/experiment
  - parses surveys
  - loads the Neo survey preset
  - resolves geography context
  - previews personas
  - runs simulations and stability checks
  - builds analysis and insights payloads
  - runs product URL and image enrichment

### 4.6 Backend API surface

Implemented routes include:

- `GET /api/v1/health`
- `GET /api/v1/models`
- `POST /api/v1/studies`
- `GET /api/v1/studies/{study_id}`
- `PATCH /api/v1/studies/{study_id}/study-mode`
- `PATCH /api/v1/studies/{study_id}/audience`
- `PATCH /api/v1/studies/{study_id}/product`
- `POST /api/v1/studies/{study_id}/product/url-autofill`
- `POST /api/v1/studies/{study_id}/product/image-analysis`
- `PATCH /api/v1/studies/{study_id}/market`
- `POST /api/v1/studies/{study_id}/survey/upload`
- `POST /api/v1/studies/{study_id}/survey/preset/neo`
- `PATCH /api/v1/studies/{study_id}/experiment`
- `GET /api/v1/studies/{study_id}/workflow`
- `POST /api/v1/studies/{study_id}/personas/preview`
- `POST /api/v1/studies/{study_id}/simulation-runs`
- `GET /api/v1/studies/{study_id}/simulation-runs/latest`
- `DELETE /api/v1/studies/{study_id}/simulation-runs/latest`
- `POST /api/v1/studies/{study_id}/simulation-runs/stability`
- `GET /api/v1/studies/{study_id}/simulation-runs/stability/latest`
- `GET /api/v1/studies/{study_id}/analysis`
- `GET /api/v1/studies/{study_id}/insights`

### 4.7 Backend behavior summary

- Study state is persisted section-by-section as JSON.
- Workflow readiness is derived from saved sections, not from frontend local state.
- Simulation runs and stability checks are synchronous request-time jobs right now.
- Analysis and insights are computed from the latest saved run result in the `jobs` table.
- Uploaded files are written to the filesystem, not blob storage.

## 5. Frontend Index

### 5.1 Frontend purpose

`apps/web` is a premium one-page workflow UI. It is not just a landing page. It is already wired to the backend for the main research flow.

### 5.2 Main entrypoints

- `apps/web/src/app/page.tsx`
  - renders the full one-page chapter sequence
- `apps/web/src/providers/app-providers.tsx`
  - wraps the app with study state and section navigation providers
- `apps/web/src/providers/study-provider.tsx`
  - creates/restores the current study and rehydrates canonical backend state
- `apps/web/src/providers/section-registry-provider.tsx`
  - controls section registration, scroll navigation, and active section behavior
- `apps/web/src/lib/api.ts`
  - all frontend API client functions and wire types

### 5.3 Frontend chapter map

The UI is organized as sequential sections:

- `main`
- `study-mode`
- `audience`
- `product`
- `market`
- `survey`
- `experiment`
- `run-simulation`
- `analysis`
- `insights`

Each section has its own component under:

- `apps/web/src/components/sections/`

### 5.4 Frontend state model

- Canonical persisted state comes from the backend.
- Unsaved drafts live locally in section components.
- `StudyProvider` auto-creates a study on first load if none is active.
- The active study id is stored in browser session/local storage.
- A mode switch creates a fresh study workspace to avoid carrying old downstream data into a new mode.

### 5.5 Frontend wiring status

The setup flow is backend-wired through `experiment`.

Also wired:

- model catalog loading
- persona preview
- simulation run launch
- latest run hydration
- stability check
- analysis fetch
- insights fetch

Known intentional limitations visible in the UI:

- some "clear/reset" actions are local-only because matching backend clear endpoints do not exist
- run progress is simulated in the UI even though the backend returns the completed result in one response
- trust framing in analysis/insights is presented as heuristic and exploratory

### 5.6 Frontend chart and utility layer

- `apps/web/src/components/charts/*`
  - reusable chart renderers
- `apps/web/src/lib/insights-chart-adapters.ts`
  - converts API payloads into chart view models
- `apps/web/src/lib/setup-flow-utils.ts`
  - seed resolution and setup messaging helpers

## 6. Environment and Dependency Index

### 6.1 Backend env vars

From `apps/api/.env.example` and current code:

Required to boot cleanly:

- `APP_ENV`
- `APP_DEBUG`
- `DATABASE_URL`
- `ARTIFACTS_ROOT`
- `LEGACY_APP_ROOT`
- `CORS_ALLOW_ORIGINS`

Optional but feature-enabling:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `GOOGLE_CLOUD_API_KEY`
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH`
- `HUD_API_TOKEN`
- `ANTHROPIC_API_KEY`

### 6.2 Frontend env vars

- `NEXT_PUBLIC_API_BASE_URL`

### 6.3 What each optional credential actually affects

- `OPENROUTER_API_KEY`
  - needed for product URL autofill
  - used to query a live model catalog
  - used by the simulation path to decide between live OpenRouter mode and mock generation
- `GOOGLE_CLOUD_API_KEY` or service account credentials
  - needed for product image analysis
- `HUD_API_TOKEN`
  - optional fallback when local HUD lookup parquet files are missing
- `ANTHROPIC_API_KEY`
  - present in settings, but not currently used by the new backend code paths inspected here

## 7. Hard Blockers vs Optional Degradations

### 7.1 Hard blockers in this checkout

Initial blockers in the raw checkout were:

- missing legacy app contents
- no backend virtualenv
- no frontend `node_modules`
- no local env files
- no `ARTIFACTS_ROOT`

Those blockers have now been resolved locally.

### 7.2 Backend hard-fail startup checks

The API startup will fail if any of these fail:

- database connectivity
- `ARTIFACTS_ROOT` exists and is writable
- `LEGACY_APP_ROOT` exists and contains `backend/`
- required Python packages import successfully

### 7.3 Degraded but not fatal conditions

- missing `OPENROUTER_API_KEY`
- missing Google Vision credentials
- missing grounding prior parquet files
- missing HUD lookup parquet files

These degrade capabilities rather than preventing the app from starting.

## 8. Testing Index

### 8.1 Backend tests

Located under `apps/api/tests`.

They cover:

- health status envelope behavior
- study creation
- study mode save
- audience save and workflow readiness
- Neo preset loading
- AYTM DOCX fallback parsing
- experiment save
- persona preview flow

Important caveat:

- several backend tests assume the legacy app and fixture files exist, which is not true in this checkout

### 8.2 Frontend tests

Located under `apps/web/tests`.

Current coverage is light and focused on pure logic:

- setup flow utility functions
- insights chart adapter transforms

## 9. Current Setup Readiness

Current local toolchain:

- Node.js `v23.11.0`
- npm `10.9.2`
- Python `3.12.7`

These version levels are modern enough for the checked manifests, and the project is now locally install-ready in this workspace.

## 10. Current Local Setup

This workspace has already been set up with:

1. a local compatibility legacy tree under `NeoSmart-Hackathon-App/`
2. `apps/api/.env`
3. `apps/web/.env.local`
4. `apps/api/artifacts/`
5. `apps/api/.venv`
6. backend dependencies installed
7. frontend dependencies installed
8. Alembic migrated local SQLite state

Optional credentials can still be added later as needed:

- OpenRouter
- Google Vision
- HUD token

## 11. Practical Conclusion

This is a real migration codebase, not just a UI mockup. The new web and API layers are already substantially wired. In this workspace, the project now runs locally with a compatibility legacy implementation, and API keys are optional follow-up configuration for richer provider-backed features.
