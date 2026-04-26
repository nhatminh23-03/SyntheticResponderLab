# SyntheticResponderLab

Premium Next.js + Python evolution of the Grounded Synthetic Respondent Lab.

This repository contains:
- a new **Next.js frontend** for the cinematic, one-page product experience
- a new **FastAPI backend** that wraps and preserves the working Python simulation logic
- the original **Streamlit prototype** kept as a reference implementation

The product helps a user:
- define a study mode
- define audience, product, market, and survey context
- configure an experiment
- run grounded synthetic respondent simulations
- inspect analysis, trust framing, and executive insights

## Repository Structure

```text
SyntheticResponderLab/
├── apps/
│   ├── api/                     # FastAPI backend for the new product
│   └── web/                     # Next.js frontend for the new product
├── Documentation/              # migration docs, specs, and implementation notes
├── UI Prototype/               # visual reference files
└── NeoSmart-Hackathon-App/     # legacy Streamlit app kept as reference
```

## Architecture

### `apps/web`
- Next.js 14
- Tailwind CSS
- Framer Motion
- premium one-page workflow UI

### `apps/api`
- FastAPI
- SQLAlchemy + Alembic
- SQLite for local development
- wraps legacy Python logic instead of rewriting it in JavaScript

### `NeoSmart-Hackathon-App`
- the original multipage Streamlit prototype
- kept in the repo as the reference logic source
- not the primary app to run for the new product

## Current Workflow

The current Next.js app includes:
- Main
- Study Mode
- Audience
- Product
- Market
- Survey
- Experiment
- Run Simulation
- Analysis
- Insights

## Prerequisites

- Node.js 18+
- npm
- Python 3.9+

## Quick Start

### 1. Backend

Create a local env file from the example:

```bash
cd apps/api
cp .env.example .env
```

Create the virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the migration:

```bash
alembic upgrade head
```

Start the API:

```bash
uvicorn src.main:app --reload --port 8000
```

### 2. Frontend

Create a local frontend env file:

```bash
cd ../web
cp .env.example .env.local
```

Install dependencies and start the app:

```bash
npm install
npm run dev
```

Open:
- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

## Environment

### Backend env

Use [`apps/api/.env.example`](apps/api/.env.example) as the template.

Important variables:
- `APP_ENV`
- `APP_DEBUG`
- `DATABASE_URL`
- `ARTIFACTS_ROOT`
- `LEGACY_APP_ROOT`
- `DEPLOYMENT_SHARED_SECRET`
- `CORS_ALLOW_ORIGINS`
- `MAX_SURVEY_UPLOAD_BYTES`
- `MAX_PRODUCT_IMAGE_UPLOAD_BYTES`
- `DAILY_STUDY_CREATE_LIMIT`
- `DAILY_UPLOAD_LIMIT`
- `DAILY_PROVIDER_RUN_LIMIT`

Production-like startup rules:
- `APP_ENV` must not be `development`, `dev`, `test`, or `local`
- `APP_DEBUG` must be `false`
- `DEPLOYMENT_SHARED_SECRET` must be configured and at least 16 characters
- `ARTIFACTS_ROOT` must exist and be writable
- `LEGACY_APP_ROOT` must exist and contain `backend/`
- `DATABASE_URL` must be a valid SQLAlchemy database URL

Optional provider credentials:
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `GOOGLE_CLOUD_API_KEY`
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH`
- `HUD_API_TOKEN`
- `ANTHROPIC_API_KEY`

### Frontend env

Use [`apps/web/.env.example`](apps/web/.env.example):

```env
API_BASE_URL=http://localhost:8000
DEPLOYMENT_SHARED_SECRET=
APP_ACCESS_PASSWORD=

# Clerk (real user auth). Required in production unless APP_ACCESS_PASSWORD
# is being used as the only gate.
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/
NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/
```

Production note:
- the web app now proxies browser API requests through Next.js server routes
- `API_BASE_URL` must point to the backend origin reachable from the web server
- `DEPLOYMENT_SHARED_SECRET` must match the backend value so the server-side proxy can reach protected API routes
- Clerk (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY`) is the primary authentication method; users sign in via Clerk and the proxy forwards trusted identity headers to the backend
- `APP_ACCESS_PASSWORD` is now **optional**. It remains available as an emergency / maintenance pre-gate that can be enabled in front of Clerk; if set in production it must be at least 12 characters. Leave empty for normal Clerk-authenticated operation
- in local development only, the web app can fall back to `http://127.0.0.1:8000` when `API_BASE_URL` is unset
- in production-like environments, missing or invalid backend env will fail during startup/build instead of silently falling back
- production builds must configure either Clerk or `APP_ACCESS_PASSWORD`; configuring neither fails fast at startup

### Authentication (Clerk)

The app uses [Clerk](https://clerk.com) as its external authentication provider.

Configure your Clerk instance:
1. Create an application in the [Clerk dashboard](https://dashboard.clerk.com).
2. Turn on **Restricted mode** so random visitors cannot sign up on their own.
3. Disable public sign-ups for every enabled authentication factor.
4. Add the application's publishable key and secret key to the frontend env (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`).
5. Admins issue invitations from the Clerk dashboard ("Users" → "Invite"); invitees receive an email link that lands on `/sign-in` and completes the Clerk ticket flow.

Backend side:
- `ADMIN_CLERK_USER_IDS` is a comma-separated list of Clerk user ids (for example, `user_2abc123,user_2def456`) that bypass study ownership checks. Keep this list short; ideally only bootstrap admins.
- `REQUIRE_AUTHENTICATED_IDENTITY=true` forces the backend to reject any request without an `X-Authenticated-User-Id` header (even outside production). Leave unset for local development so the dev-fallback synthetic user continues to work.
- `DEV_FALLBACK_USER_ID` controls the synthetic user id used for local / test environments when identity headers are not present (defaults to `dev-local-user`). Production ignores this fallback.
- Daily quota env vars are enforced server-side per authenticated user:
  - `DAILY_STUDY_CREATE_LIMIT`
  - `DAILY_UPLOAD_LIMIT` (shared by survey upload and product image analysis)
  - `DAILY_PROVIDER_RUN_LIMIT` (shared by simulation runs, stability checks, and interview runs)

Identity trust boundary:
- Browsers never call the FastAPI backend directly.
- The Next.js server proxy at `apps/web/src/app/api/backend/[...path]/route.ts` resolves the current Clerk session via `auth()`, strips any client-supplied `X-Authenticated-*` headers, and injects trusted `X-Authenticated-User-Id`, `X-Authenticated-User-Email`, and `X-Authenticated-Auth-Mode` headers alongside the existing `X-Deployment-Secret`.
- FastAPI's `get_current_user` dependency reads those proxy-injected headers. Requests that reach the backend without the deployment shared secret are rejected before identity is considered.

### Cutover (pre-Clerk → Clerk)

Run these steps once when switching a deployment from the shared-password gate to Clerk:
1. Configure Clerk (keys, Restricted mode, invitees) as described above.
2. Deploy the new frontend and backend with Clerk env vars set.
3. Decide on a bootstrap admin Clerk user id (one of the admins you invited, typically the first user listed in `ADMIN_CLERK_USER_IDS`).
4. Reassign pre-existing studies that have `owner_user_id = NULL` (or a `legacy:` placeholder owner) to the bootstrap admin so they remain accessible:
   ```bash
   .venv/bin/python apps/api/scripts/backfill_study_owners.py \
     --owner user_2abcBootstrap \
     --match-legacy \
     --dry-run
   # inspect the output, then rerun without --dry-run to apply
   ```
5. Leave `APP_ACCESS_PASSWORD` unset in prod under normal operation. It is only needed if you intentionally want an emergency maintenance pre-gate in front of Clerk.

### Public-launch anti-abuse safeguards

The app now enforces these protections in code:
- per-user daily study creation limits
- per-user daily upload limits
- per-user daily provider-run limits
- one provider-backed run in flight per user at a time

API behavior:
- `429 quota_exceeded` means the authenticated user has reached today’s limit for that action
- `409 provider_run_in_flight` means the authenticated user already has a provider-backed run in progress

Recommended edge/platform protections:
- Clerk owns password security, sign-in, and invite acceptance. Do **not** rebuild local login throttling in the app.
- Configure rate limits at the hosting edge for:
  - `/sign-in`
  - `/sign-up`
  - Clerk callback routes used by your deployment
  - `/api/backend/*` as defense-in-depth
- Conservative starting points:
  - unauthenticated auth-entry routes: `10 requests/min/IP`
  - authenticated `/api/backend/*`: `60 requests/min/IP`, then tune based on real traffic

Suggested Clerk dashboard settings:
- Restricted mode enabled
- public sign-ups disabled
- invitations issued by admins only
- bot protection / abuse safeguards enabled where available

### Deployment assumptions

This app is not fully self-contained yet. A real deployment must provide:
- the `apps/api` service
- the `apps/web` service
- a writable artifacts directory for the API
- the legacy runtime tree referenced by `LEGACY_APP_ROOT`

If any of those assumptions are missing, backend startup or health checks will fail loudly.

## Deployment Protection Model

The production-minded access-control stack is layered:

- the backend API is protected by `DEPLOYMENT_SHARED_SECRET` (shared between the frontend server and the backend)
- real user identity is provided by **Clerk** on the frontend; users must sign in to render the authenticated app shell
- browser requests hit the Next.js app first and are routed through the Next.js server proxy for every backend call
- the proxy resolves the Clerk session server-side, strips any client-supplied identity headers, and injects trusted `X-Authenticated-User-Id` / `X-Authenticated-User-Email` / `X-Authenticated-Auth-Mode` headers alongside `X-Deployment-Secret`
- FastAPI enforces per-user study ownership: studies are owned by the Clerk user id that created them, and non-owners get a 403 unless they are listed in `ADMIN_CLERK_USER_IDS`
- `APP_ACCESS_PASSWORD` is an **optional** emergency pre-gate that can be turned on in front of Clerk if needed; normal operation leaves it empty

This means anonymous users cannot:
- see the authenticated product shell (only the public landing page)
- call the protected frontend proxy routes (proxy returns 401)
- directly call backend study/upload/simulation routes without the shared secret
- impersonate another user by setting `X-Authenticated-*` headers manually (the proxy always overwrites them)

Design notes:
- the backend does not verify Clerk JWTs directly today; trust flows through the proxy + `DEPLOYMENT_SHARED_SECRET`. Adding JWT verification on the FastAPI side is a future defense-in-depth step.
- if Clerk is not configured, the app falls back to the legacy shared-password gate; this is intended only for maintenance or emergency operation.

## Testing

### Backend

```bash
cd apps/api
source .venv/bin/activate
pytest -q
```

### Frontend

```bash
cd apps/web
npm run test:unit
npm run build
```

## Important Notes Before Pushing To GitHub

- Do **not** commit local `.env` files.
- Do **not** commit local database files like `local-dev.db`.
- Do **not** commit generated artifacts under `apps/api/artifacts/`.
- Do **not** commit `node_modules/` or virtual environments.
- The root `.gitignore` in this repo is set up to ignore those.
- Local credential-like JSON files are also ignored now, including common service-account filename patterns.

One important security note:
- if you previously stored a real provider key in a local `.env`, rotate that key before publishing the repository if there is any chance it was ever exposed

Optional local commit guard:

```bash
pip install pre-commit
pre-commit install
```

This repo now includes a lightweight staged-secret check that blocks obvious private keys and Google service-account JSON from being committed.

## Legacy Reference App

The old Streamlit app lives in [`NeoSmart-Hackathon-App/`](NeoSmart-Hackathon-App/).

It remains useful for:
- validating behavior against the original prototype
- tracing legacy grounding, survey parsing, simulation, analysis, and insights logic
- understanding the migration history

The new product work should happen in:
- [`apps/api/`](apps/api/)
- [`apps/web/`](apps/web/)

## Suggested Git Setup

This workspace is not currently initialized as a git repository from the root.

If you want to publish from this root folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Documentation

Project planning and migration notes are in [`Documentation/`](Documentation/).

Deployment operators should start with:
- [`Documentation/invite-only-deployment-runbook.md`](Documentation/invite-only-deployment-runbook.md)
- [`Documentation/vercel-render-deployment.md`](Documentation/vercel-render-deployment.md)

Key docs include:
- frontend migration review
- Next.js + Python migration plan
- Phase 0 backend spec
- Phase 1 backend implementation notes
- Phase 2 setup flow hardening notes
- Phase 3 chart system plan
