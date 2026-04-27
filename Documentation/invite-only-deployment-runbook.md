# Invite-Only Deployment Runbook and Release Readiness

This document is the operator-facing runbook for deploying the current app as an invite-only public beta.

It remains useful as the platform-neutral checklist. For the selected Vercel + Render deployment target, use this alongside [`vercel-render-deployment.md`](vercel-render-deployment.md).

## A. Executive summary

The app is close to deployable for an invite-only launch.

What is already hardened in code:
- Clerk is the primary auth system
- logged-out users see the public landing shell
- Render-style backend wake-up readiness is handled before workflow entry
- logged-in users use the authenticated workflow shell
- the Next.js proxy injects trusted identity headers and strips spoofed browser headers
- FastAPI enforces study ownership and admin override via `ADMIN_CLERK_USER_IDS`
- the backend enforces per-user daily quotas
- the backend blocks concurrent provider-backed runs per user
- upload and URL-autofill security guardrails are in place

What still depends on the operator:
- Clerk production configuration
- web and API environment configuration
- database provisioning and migrations
- writable artifacts storage
- deployment of the legacy runtime tree referenced by `LEGACY_APP_ROOT`
- edge/platform rate limiting for Clerk entry routes and `/api/backend/*`

Current recommendation:
- the app is suitable for **invite-only deployment** if the required environment, Clerk, filesystem, and edge controls are configured correctly
- it is **not yet a fully self-serve public product** because operator-side rate limiting and platform deployment definition still live outside the repo

## B. Deployment prerequisites

### Required services and accounts

You need all of the following before launch:

1. A Clerk application
2. A database reachable by `apps/api`
3. A host for the Next.js frontend (`apps/web`)
4. A host for the FastAPI backend (`apps/api`)
5. A writable filesystem location for `ARTIFACTS_ROOT`
6. The legacy runtime tree available on the API host for `LEGACY_APP_ROOT`

### Required repo/runtime assumptions

These assumptions are enforced by code or startup checks:

| Area | Requirement | Enforced by app | Notes |
|---|---|---:|---|
| Backend secret | `DEPLOYMENT_SHARED_SECRET` set and at least 16 chars in production-like env | Yes | Required for proxy-to-backend trust |
| Backend debug | `APP_DEBUG=false` in production-like env | Yes | Startup fails otherwise |
| Backend database | `DATABASE_URL` valid | Yes | Startup fails if invalid |
| Artifacts storage | `ARTIFACTS_ROOT` exists and is writable | Yes | Startup fails otherwise |
| Legacy runtime | `LEGACY_APP_ROOT` exists and contains `backend/` | Yes | Startup fails otherwise |
| Python deps | Required backend packages import successfully | Yes | Startup fails otherwise |
| Clerk config | Publishable + secret key configured in frontend | Yes, at build/start | Required unless intentionally using legacy maintenance gate |
| Backend origin | `API_BASE_URL` or `NEXT_PUBLIC_API_BASE_URL` valid in frontend | Yes, at build/start | No production localhost fallback |
| Edge rate limits | Limits on Clerk entry routes and `/api/backend/*` | No | Must be configured outside app code |
| Platform manifests | Docker/platform config | Partial | Vercel + Render config exists; other hosts need equivalent config |

### Optional dependencies that degrade health but do not hard-fail startup

The health endpoint can return `degraded` while startup still succeeds if these are missing:
- `OPENROUTER_API_KEY`
- Google Vision credentials:
  - `GOOGLE_CLOUD_API_KEY`, or
  - `GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON`, or
  - `GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH`
- grounding prior files under `LEGACY_APP_ROOT/data/processed/priors`
- local HUD lookup files under `LEGACY_APP_ROOT/data/processed/lookups`
- `HUD_API_TOKEN` when local HUD lookups are absent

These are acceptable for invite-only beta **only if** you understand the impact:
- missing OpenRouter blocks real provider-backed generation
- missing Google Vision degrades image analysis
- missing priors/lookups degrades persona/grounding quality

## C. Required env and platform configuration

### Frontend (`apps/web`) required env

Required for normal Clerk-based invite-only deployment:

```env
API_BASE_URL=https://api.example.com
DEPLOYMENT_SHARED_SECRET=<same-value-as-backend>

NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<clerk-publishable-key>
CLERK_SECRET_KEY=<clerk-secret-key>
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL=/
NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL=/
```

Optional:

```env
APP_ACCESS_PASSWORD=<optional-maintenance-pre-gate>
```

Use `APP_ACCESS_PASSWORD` only if you intentionally want a maintenance gate in front of Clerk. Leave it unset for normal invite-only launch.

### Backend (`apps/api`) required env

Required:

```env
APP_ENV=production
APP_DEBUG=false
DATABASE_URL=<real-db-url>
ARTIFACTS_ROOT=<writable-absolute-or-resolved-path>
LEGACY_APP_ROOT=<path-to-NeoSmart-Hackathon-App>
DEPLOYMENT_SHARED_SECRET=<same-value-as-frontend>
CORS_ALLOW_ORIGINS=https://app.example.com
ADMIN_CLERK_USER_IDS=user_xxx,user_yyy
REQUIRE_AUTHENTICATED_IDENTITY=true
```

Recommended defaults for current quota model:

```env
MAX_SURVEY_UPLOAD_BYTES=8388608
MAX_PRODUCT_IMAGE_UPLOAD_BYTES=5242880
DAILY_STUDY_CREATE_LIMIT=20
DAILY_UPLOAD_LIMIT=50
DAILY_PROVIDER_RUN_LIMIT=20
```

Optional provider/data env:

```env
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
GOOGLE_CLOUD_API_KEY=
GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=
GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=
HUD_API_TOKEN=
ANTHROPIC_API_KEY=
```

### Clerk configuration required outside the repo

Configure Clerk with all of the following:
- Restricted mode enabled
- public sign-up disabled
- invitations issued by admins only
- production frontend URL added to allowed origins / redirect settings
- sign-in and sign-up flows pointed at:
  - `/sign-in`
  - `/sign-up`
- invite acceptance flow tested against production URLs

### Required edge/platform protections

These protections are **not** enforced by the app and must be configured at the host or edge:
- rate limits on `/sign-in`
- rate limits on `/sign-up`
- rate limits on Clerk callback routes
- rate limits on `/api/backend/*`

Recommended starting points:
- unauthenticated Clerk/auth entry routes: `10 requests/min/IP`
- authenticated `/api/backend/*`: `60 requests/min/IP`

If your platform supports bot protection or WAF rules, enable them on Clerk entry routes.

## D. Deployment runbook

Follow this order exactly.

### 1. Provision external services

Create or confirm:
- Clerk production application
- production database
- frontend hosting target
- backend hosting target
- persistent writable directory or mounted volume for `ARTIFACTS_ROOT`

### 2. Stage the legacy runtime on the API host

The backend still depends on the legacy tree.

Before backend startup, ensure:
- the repository or deploy artifact includes `NeoSmart-Hackathon-App/`, or
- the host mounts/provisions that directory separately

`LEGACY_APP_ROOT` must resolve to a directory that contains:
- `backend/`
- `data/processed/priors` for prior files if available
- `data/processed/lookups` for HUD lookup files if available

If this path is wrong, backend startup fails.

### 3. Configure Clerk for invite-only launch

In Clerk:
1. turn on Restricted mode
2. disable public self-sign-up
3. create at least one admin invite
4. confirm production sign-in and sign-up URLs
5. note the Clerk user id(s) for bootstrap admins

Block launch if:
- public sign-up is still enabled
- callback/redirect URLs do not match deployed frontend origin

### 4. Configure backend environment

Set all required backend env vars.

Before starting the backend:
- create `ARTIFACTS_ROOT`
- ensure it is writable by the API process
- confirm `DATABASE_URL` points to the production database
- set `REQUIRE_AUTHENTICATED_IDENTITY=true`
- populate `ADMIN_CLERK_USER_IDS` with the initial admin Clerk user ids

### 5. Run database migrations

From `apps/api`:

```bash
alembic upgrade head
```

Block launch if migrations fail.

### 6. Start the backend and verify health

Start the API process, then call:

```bash
GET /api/v1/health
```

Expected:
- `200` with `status=ok` or `status=degraded`
- `503` means launch is blocked

Interpretation:
- `failed` / `503` = do not proceed
- `degraded` = proceed only if the degraded checks are truly optional for your beta

### 7. Configure frontend environment

Set all required frontend env vars:
- backend API origin
- deployment shared secret
- Clerk keys
- Clerk auth URLs

Only set `APP_ACCESS_PASSWORD` if you intentionally want the maintenance pre-gate enabled.

### 8. Deploy the frontend

Deploy `apps/web` and verify:
- the logged-out landing shell renders
- `/api/readiness` can reach the backend health endpoint
- the server-side proxy can reach the backend
- Clerk routes function against production origin

Block launch if:
- frontend build/start fails due to env validation
- readiness never reports ready while backend health is `ok` or `degraded`
- the frontend cannot reach the backend through the proxy

### 9. Backfill studies with null or legacy owners

Run the backfill script after Clerk auth is live and before opening access to invited users.

Dry run first:

```bash
.venv/bin/python apps/api/scripts/backfill_study_owners.py \
  --owner user_bootstrap_admin \
  --match-legacy \
  --dry-run
```

Then apply:

```bash
.venv/bin/python apps/api/scripts/backfill_study_owners.py \
  --owner user_bootstrap_admin \
  --match-legacy
```

Block launch if unowned studies remain and you need existing data to be accessible.

### 10. Configure edge protections

Before invite-only launch, apply:
- rate limits to Clerk auth entry routes
- rate limits to `/api/backend/*`
- any platform bot-protection / WAF rules available

This is required because the app does not enforce edge throttling itself.

### 11. Verify backend wake-up behavior

If your backend host can sleep, restart or sleep the backend and open the frontend.

Expected:
- public landing shell still renders
- `/api/readiness` polls the backend
- login and invite entry points remain inactive until readiness is confirmed
- signed-in users see the wake-up screen until the backend is ready

Block launch if the app renders blank, enables workflow actions while the backend is unavailable, or never recovers after backend health returns `ok` or `degraded`.

### 12. Cut over to production URLs

Final cutover order:
1. backend healthy and reachable
2. frontend deployed with correct backend origin and Clerk keys
3. Clerk redirect/callback URLs confirmed
4. owner backfill completed
5. admin user can sign in successfully
6. edge protections enabled
7. invite first external beta users

## E. Post-deploy smoke-test checklist

Use at least:
- one admin test user
- one normal invited user
- one second normal invited user for ownership isolation checks
- one small valid survey file
- one small valid product image
- one safe public product URL
- one blocked internal-style URL such as `http://127.0.0.1:8000`

### Logged-out checks

1. Open `/`
   - expected: public landing shell
   - blocker if: app shell appears while logged out

2. Open `/sign-in`
   - expected: Clerk sign-in flow
   - blocker if: route broken or redirects incorrectly

3. Accept a fresh invite
   - expected: invite ticket flow completes and lands in app
   - blocker if: invite flow fails

### Logged-in checks

4. Sign in as invited user
   - expected: authenticated workflow shell loads
   - blocker if: user lands on public shell after successful Clerk sign-in

5. Restart or sleep the backend, then open the frontend
   - expected: public landing still renders and `/api/readiness` eventually enables workflow entry
   - blocker if: the app renders blank or allows workflow entry while backend remains unavailable

6. Create a study
   - expected: succeeds and persists
   - blocker if: study create fails

7. Verify ownership isolation
   - user A creates a study
   - user B attempts to access the same study URL or workflow state
   - expected: user B is denied
   - blocker if: cross-user access succeeds

8. Upload a valid survey file
   - expected: upload succeeds
   - blocker if: normal small valid file fails

9. Upload an invalid or oversize survey file
   - expected: clean validation error
   - acceptable if: message text needs polish
   - blocker if: request crashes or hangs

10. Product URL autofill with a safe public URL
   - expected: succeeds
   - blocker if: known-safe public URL is always rejected

11. Product URL autofill with blocked URL
    - expected: clean validation rejection
    - blocker if: internal/private targets are accepted

12. Upload a valid product image
    - expected: succeeds or degrades gracefully if optional image-analysis credentials are absent
    - blocker if: feature crashes

13. Start a simulation run
    - expected: run starts successfully
    - blocker if: provider-backed operation is broken for a valid configured account

14. Attempt a second provider-backed run while the first is active
    - expected: `provider_run_in_flight` behavior with clean UI copy
    - acceptable if: exact wording differs
    - blocker if: duplicate run starts anyway

15. Force a quota-exceeded condition with a lowered test limit
    - expected: clean `quota_exceeded` behavior in API and UI
    - acceptable if: copy is generic but understandable
    - blocker if: unlimited usage still succeeds

16. Load analysis
    - expected: analysis view renders
    - blocker if: analysis route crashes for a valid completed run

17. Load insights
    - expected: insights view renders
    - blocker if: insights route crashes for a valid completed run

18. Log out
    - expected: return to logged-out state / public landing shell
    - blocker if: session remains authenticated after logout

19. If `APP_ACCESS_PASSWORD` is intentionally enabled, test maintenance pre-gate
    - expected: user must pass maintenance gate before Clerk
    - acceptable to skip if maintenance gate is not enabled in production

## F. Remaining risks

### Must fix before invite-only launch

These are true launch blockers if still unresolved in your deployment:
- missing or incorrect Clerk production configuration
- missing or invalid production env vars
- backend health returning `failed` / `503`
- absent or broken `LEGACY_APP_ROOT`
- no writable `ARTIFACTS_ROOT`
- database migrations not applied
- no edge/platform rate limits configured for Clerk entry routes and `/api/backend/*`
- owner backfill not completed when legacy/null-owner data must be retained

### Recommended soon after launch

- add automated deployment checks around the Vercel + Render configuration
- add automated production smoke checks in CI or your host
- add backend-side JWT verification against Clerk as defense in depth
- monitor quota pressure and tune the default limits with real usage
- add structured operational dashboards/logging around provider-backed runs

### Acceptable deferred items for invite-only beta

- billing
- teams/orgs
- full admin console
- public self-sign-up
- broader public beta readiness work

## Final recommendation

**READY FOR INVITE-ONLY DEPLOYMENT WITH KNOWN RISKS**

Why:
- the app-level launch-critical protections appear to be in place
- the backend has startup guardrails and health classification
- auth, ownership, quotas, and in-flight protection are already implemented
- the remaining material risks are mostly operator-side rather than product-code gaps

The known risks that still matter:
- the deployment still depends on the legacy runtime tree
- edge/platform rate limiting is required but external to app code
- the repo still lacks platform-specific deployment manifests, so deployment is not one-command reproducible yet
- optional provider/data dependencies can still leave the system `degraded` depending on your beta scope

If you can satisfy the runbook and pass the smoke test checklist above, the current codebase is in good shape for an invite-only launch.
