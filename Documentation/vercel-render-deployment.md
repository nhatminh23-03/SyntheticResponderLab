# Vercel + Render Deployment Definition

This document defines the recommended real-hosting target for the current codebase.

## A. Platform deployment architecture

### Recommended hosting split

- Frontend: **Vercel**
- Backend: **Render Web Service** using Docker
- Database: **Neon Postgres** for a free deployment, or Render Postgres for a paid Render-only setup
- Storage/artifacts: **Render persistent disk** mounted into the backend service
- Edge rate limiting: **Vercel Firewall / WAF rate limiting**

### Render cold starts

If the Render backend is on a free or sleeping tier, the frontend uses a public Next.js readiness check at `/api/readiness` to wake and poll the FastAPI health endpoint.

Expected behavior:
- logged-out landing content renders immediately
- login / invite entry points stay disabled until backend readiness is confirmed
- signed-in users see a wake-up screen instead of a half-loaded workflow
- once `/api/v1/health` returns `ok` or `degraded`, workflow access is enabled
- if the backend takes too long, the UI shows a retry state

### Why this is the recommended split

This backend is not a good fit for Vercel serverless hosting in its current shape because it requires:
- a writable persistent `ARTIFACTS_ROOT`
- an on-disk `LEGACY_APP_ROOT`
- long-lived Python request handling for provider-backed operations

Official platform docs support that recommendation:
- Vercel functions have a **read-only filesystem** with only writable `/tmp` scratch space up to 500 MB: [Vercel runtimes](https://vercel.com/docs/functions/runtimes)
- Render supports **persistent disks** for web services and Docker workloads: [Render persistent disks](https://render.com/docs/disks)
- Render Blueprints support Docker services, disks, health checks, env vars, and Postgres wiring: [Render Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- Vercel provides WAF rate limiting rules suitable for Clerk entry routes and `/api/backend/*`: [Vercel WAF rate limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)

### Network and trust boundary

Production request flow:

1. Browser → Vercel frontend (`apps/web`)
2. Vercel Next.js proxy → Render backend (`apps/api`)
3. Render backend → Postgres, typically Neon on the free path
4. Render backend → Render persistent disk at `ARTIFACTS_ROOT`

Trust boundary:
- browsers never call the backend directly in the intended architecture
- Vercel injects `X-Deployment-Secret`
- Vercel injects trusted `X-Authenticated-*` headers after resolving Clerk session
- FastAPI rejects protected routes without the deployment secret

## B. Required repo/config changes

This repo now includes the minimum platform-specific definitions for this target:

- [`.dockerignore`](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/.dockerignore)
  - trims the Docker build context for the Render backend image
- [`apps/api/Dockerfile`](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/api/Dockerfile)
  - builds the FastAPI service and fetches the pinned legacy runtime tree into the image
- [`render.yaml`](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/render.yaml)
  - defines the Render backend service and paid Render Postgres option; for free Neon deployments, create only the backend service manually and paste the Neon `DATABASE_URL`
- [`apps/web/vercel.json`](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/web/vercel.json)
  - locks the Vercel project to the expected Next.js build/install commands

### Platform project setup

#### Vercel

Create a Vercel project with:
- **Root Directory**: `apps/web`
- framework auto-detected as Next.js
- production domain set to your app domain

#### Render

Create the backend via the root [`render.yaml`](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/render.yaml), or manually mirror its configuration in the Render dashboard.

## C. Env/secrets matrix

### Frontend: Vercel project env

Required:

| Variable | Required | Notes |
|---|---:|---|
| `API_BASE_URL` | Yes | Example: `https://synthetic-responder-api.onrender.com` |
| `DEPLOYMENT_SHARED_SECRET` | Yes | Must match backend exactly |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes | Clerk publishable key |
| `CLERK_SECRET_KEY` | Yes | Clerk secret key |
| `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | Yes | Usually `/sign-in` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | Yes | Usually `/sign-up` |
| `NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL` | Yes | Usually `/` |
| `NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL` | Yes | Usually `/` |

Optional:

| Variable | Required | Notes |
|---|---:|---|
| `APP_ACCESS_PASSWORD` | No | Optional maintenance pre-gate only |

Do **not** rely on `NEXT_PUBLIC_API_BASE_URL` for production unless intentionally using it as the fallback input. Prefer `API_BASE_URL`.

### Backend: Render env

Required:

| Variable | Required | Notes |
|---|---:|---|
| `APP_ENV` | Yes | `production` |
| `APP_DEBUG` | Yes | `false` |
| `DATABASE_URL` | Yes | Neon pooled Postgres connection string on the free path, or Render Postgres connection string on the paid path |
| `ARTIFACTS_ROOT` | Yes | `/var/data/artifacts` |
| `LEGACY_APP_ROOT` | Yes | `/app/NeoSmart-Hackathon-App` |
| `DEPLOYMENT_SHARED_SECRET` | Yes | Must match frontend |
| `CORS_ALLOW_ORIGINS` | Yes | Frontend origin, e.g. `https://app.example.com` |
| `ADMIN_CLERK_USER_IDS` | Yes | Comma-separated Clerk admin user ids |
| `REQUIRE_AUTHENTICATED_IDENTITY` | Yes | `true` |

Quota / upload limits:

| Variable | Required | Default in blueprint |
|---|---:|---:|
| `MAX_SURVEY_UPLOAD_BYTES` | Yes | `8388608` |
| `MAX_PRODUCT_IMAGE_UPLOAD_BYTES` | Yes | `5242880` |
| `DAILY_STUDY_CREATE_LIMIT` | Yes | `20` |
| `DAILY_UPLOAD_LIMIT` | Yes | `50` |
| `DAILY_PROVIDER_RUN_LIMIT` | Yes | `20` |

Optional provider/data env:

| Variable | Required | Notes |
|---|---:|---|
| `OPENROUTER_API_KEY` | Optional | Needed for live provider-backed runs |
| `OPENROUTER_BASE_URL` | Optional | Defaults to OpenRouter API URL |
| `GOOGLE_CLOUD_API_KEY` | Optional | One valid Google Vision credential option |
| `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON` | Optional | Alternative credential option |
| `GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH` | Optional | Alternative credential option |
| `HUD_API_TOKEN` | Optional | Allows HUD API fallback if local lookups are missing |
| `ANTHROPIC_API_KEY` | Optional | Optional provider path |

### Clerk production config

Required in Clerk dashboard:
- Restricted mode enabled
- public sign-up disabled
- invite-only onboarding via admin invites
- production frontend URL configured
- sign-in URL: `https://<frontend-domain>/sign-in`
- sign-up URL: `https://<frontend-domain>/sign-up`
- invite acceptance tested against the production frontend origin

## D. Legacy runtime strategy

`LEGACY_APP_ROOT` will exist in deployment by being **fetched into the backend Docker image** from the pinned legacy runtime repository and commit.

Concrete path:
- container path: `/app/NeoSmart-Hackathon-App`
- backend env:
  - `LEGACY_APP_ROOT=/app/NeoSmart-Hackathon-App`
- Docker build args:
  - `LEGACY_APP_REPO=https://github.com/ytun1/NeoSmart-Hackathon-App.git`
  - `LEGACY_APP_REV=0d066c1ddc963e562cc699a6a43f2d1e91c46828`

Why this is the simplest safe choice:
- no separate mount is required for the legacy source tree
- backend startup checks can validate it deterministically
- the image contains the exact runtime tree the backend expects

Operational implication:
- any backend deploy that changes the repo will rebuild the image and refresh the embedded legacy tree

## E. Storage strategy

### `ARTIFACTS_ROOT`

Recommended value on Render:

```env
ARTIFACTS_ROOT=/var/data/artifacts
```

### Why local disk on Render is acceptable here

The current app uses filesystem-backed artifact storage via the backend, not object storage.
For this codebase, the smallest practical production shape is:
- one Render web service
- one attached persistent disk
- one backend instance

That aligns with the current app assumptions.

### Important constraints

- local disk is acceptable **only because** Render persistent disks preserve data across restarts and deploys
- only data written under the mounted disk path persists
- the backend service should remain a **single instance** when using this disk-backed artifact model
- this is appropriate for invite-only beta, but not the ideal long-term storage architecture for a larger public product

## F. Rate limiting / edge protection

### Where rate limiting should live

Because Clerk owns auth and the browser only talks to Vercel, configure rate limiting at **Vercel Firewall / WAF**.

Required rules:

1. `/sign-in`
   - start with `10 requests/min/IP`
2. `/sign-up`
   - start with `10 requests/min/IP`
3. Clerk callback routes used by your production flow
   - start with `10 requests/min/IP`
4. `/api/backend/*`
   - start with `60 requests/min/IP`

Recommended actions:
- begin with `Log` in staging if needed
- switch to `429` rate limiting for production
- enable any additional Vercel bot or firewall protections available

### If Vercel WAF/rate limiting is unavailable on your plan

Smallest practical fallback:
- place the frontend behind Cloudflare
- configure equivalent path-based rate limits there

Do **not** treat documented rate limits as “done” if they are not actually configured on the platform.

## G. Staging rollout checklist

### 1. Provision services

1. Create the Vercel project rooted at `apps/web`
2. Create a Neon Postgres database for the free path
3. Create the Render backend as a Docker web service using [`apps/api/Dockerfile`](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/apps/api/Dockerfile)
4. Skip the Render persistent disk on the fully-free path; uploaded/generated filesystem artifacts will be ephemeral until object storage or a paid Render disk is added
4. Create the Clerk production or staging app

### 2. Set secrets

Set all required:
- Vercel frontend env
- Render backend env
- matching `DEPLOYMENT_SHARED_SECRET`
- Clerk keys
- `ADMIN_CLERK_USER_IDS`

### 3. Run migrations

The backend Docker startup runs:

```bash
alembic upgrade head
```

before starting Uvicorn. This is intentional for the Render free path where a separate shell or pre-deploy command may not be available. On first backend boot, Neon should receive the required tables automatically.

### 4. Backfill owners if needed

If any existing studies still have `owner_user_id = NULL` or `legacy:*`, run:

```bash
cd /app
python apps/api/scripts/backfill_study_owners.py \
  --owner <bootstrap-admin-clerk-user-id> \
  --match-legacy \
  --dry-run
```

Then rerun without `--dry-run`.

### 5. Deploy backend

Deploy the Render backend and verify:
- service starts successfully
- `/api/v1/health` returns `200`
- status is `ok` or an understood `degraded`

### 6. Deploy frontend

Deploy the Vercel frontend and verify:
- build passes
- public landing shell appears while logged out
- `/sign-in` and `/sign-up` routes work
- proxy calls can reach the Render backend

### 7. Verify Clerk config

Confirm:
- restricted mode enabled
- public sign-up disabled
- production URLs/callbacks correct
- admin invites work

### 8. Run smoke tests

Execute the smoke-test list from [invite-only-deployment-runbook.md](/Users/mnd/Desktop/AI%20Hackathon/SyntheticResponderLab/Documentation/invite-only-deployment-runbook.md), especially:
- invite acceptance
- ownership isolation with two users
- simulation run
- in-flight blocking
- quota exceeded behavior
- safe URL autofill rejection

## H. Final platform readiness note

**READY TO DEPLOY TO STAGING**

Why:
- the codebase now has a concrete platform fit
- the backend runtime needs are met by Render
- the frontend runtime needs are met naturally by Vercel
- the repo now includes the minimum deployment definition files for this architecture

**Not yet automatically “READY TO DEPLOY TO PRODUCTION”** until:
- Clerk production config is actually applied
- edge rate limiting is actually configured in Vercel
- migrations and owner backfill are completed
- a real staging smoke test passes end to end

### Bottom-line recommendation

For this codebase:
- **Vercel frontend + Render backend** is the better choice
- **Vercel frontend + Vercel backend** is not recommended right now

The decisive reason is backend runtime fit: persistent writable storage and a stable bundled legacy runtime tree are first-class requirements today.
