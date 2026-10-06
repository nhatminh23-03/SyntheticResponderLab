## Public Deployment Hardening: Minimal Path to Real Launch

> Status note (April 2026): the repo has since adopted **Clerk** as the auth foundation.
> The app-owned auth sections below are now historical context, not the recommended implementation path.
> The still-relevant follow-on work from this document is anti-abuse hardening: per-user quotas, in-flight provider-run guards, and edge/platform rate limiting around Clerk entry routes and backend proxy traffic.

### A. Public-deployment blocker list
The current app is **not yet suitable for fully public launch** because these four controls are still missing or incomplete:

1. **Real user identity**
   - Current protection is a shared app password, not user authentication.
   - There is no durable user/session model, so access cannot be tied to an individual account.

2. **Per-user authorization**
   - Studies already have `owner_user_id`, but the backend does not currently derive or enforce it from authenticated identity.
   - Any authenticated browser user would still effectively act as a shared operator unless ownership checks are added.

3. **Brute-force and rate limiting**
   - The current access gate has no real login-attempt throttling.
   - Provider-backed operations need request-rate and daily-usage controls to avoid abuse/cost spikes.

4. **Usage/cost safeguards**
   - There is no per-user limit on study creation, uploads, simulations, or interview runs.
   - Public launch needs a minimal quota model even before billing exists.

### B. Recommended auth/access architecture
Use the **smallest app-owned, invite-only auth model** that fits the existing architecture.

**Chosen model**
- **Invite-only local accounts** with email + password
- **Backend-owned users and sessions**
- **Next.js middleware/session cookie** for UI gating
- **Backend remains protected by the existing deployment shared secret**
- **Frontend proxy forwards trusted user identity to the backend**
- **No public signup in v1**
- **No external auth vendor in v1**

**Why this is the smallest realistic fit**
- The backend already has `owner_user_id` on `Study`, so we can reuse that immediately.
- The app already has a Next.js middleware gate and a backend proxy; we can replace the shared-password gate rather than invent a second auth path.
- Invite-only avoids signup, email verification, anti-spam onboarding, and account-recovery complexity at launch.

**Target architecture**
- Add backend tables:
  - `users`
  - `auth_sessions`
  - `auth_login_attempts`
  - `user_usage_counters`
- Add backend auth endpoints:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
- Add backend auth dependency:
  - resolves authenticated user from trusted proxy headers
  - rejects missing/invalid identity for protected routes
- Add Next.js auth/session layer:
  - repurpose the current `/access` flow into `/login`
  - issue an HTTP-only signed session cookie
  - middleware checks session presence/validity and redirects to login
- Keep backend non-public in practice:
  - all browser traffic should go through Next.js
  - backend still requires `DEPLOYMENT_SHARED_SECRET`
- Authorization model:
  - normal users can access only their own studies/jobs/assets
  - admin users can view/manage all records
- Rate limiting model:
  - **edge/proxy rate limiting** for unauthenticated/login traffic
  - **app-level per-user quotas** for expensive operations

**Public interface/type changes**
- `StudyCreateRequest.owner_user_id` becomes ignored/removed from client control; backend sets owner from authenticated user
- all study/job endpoints become authenticated
- new user/session payloads:
  - `AuthUser { user_id, email, role, status }`
  - `AuthSession { session_id, expires_at }`
- new auth env vars:
  - `SESSION_SIGNING_SECRET`
  - `INITIAL_ADMIN_EMAIL`
  - `INITIAL_ADMIN_PASSWORD` or bootstrap command equivalent
  - `LOGIN_MAX_ATTEMPTS`
  - `LOGIN_WINDOW_MINUTES`
  - `LOGIN_BLOCK_MINUTES`
  - `DAILY_STUDY_CREATE_LIMIT`
  - `DAILY_UPLOAD_LIMIT`
  - `DAILY_PROVIDER_RUN_LIMIT`
  - `APP_ACCESS_PASSWORD` becomes optional, not required

### C. Smallest implementation slice
This is the first slice that gets the app from “shared gate” to “real public-launch-capable core.”

#### 1. Authentication
Implement invite-only email/password auth with local accounts.

**Backend**
- Add `User` model:
  - `id`, `public_id`, `email`, `password_hash`, `role`, `status`, `created_at`, `disabled_at`, `last_login_at`
- Add `AuthSession` model:
  - `id`, `user_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at`, `last_seen_at`, `created_ip`, `user_agent`
- Add password hashing with `argon2` or `bcrypt` (recommend `argon2`)
- Add login/logout/me endpoints
- Add bootstrap path:
  - simplest version: CLI/admin command to create the first admin user
  - no public signup route

**Frontend**
- Replace the shared-password `/access` screen with a real `/login` screen
- After successful login:
  - set a signed HTTP-only session cookie
  - store only session identity metadata needed for middleware gating
- Middleware:
  - redirect unauthenticated users to `/login`
  - allow static assets, login routes, and health/proxy internals as needed

#### 2. Per-user access control
Implement ownership enforcement end to end.

**Backend**
- Add an authenticated-user dependency for all protected study routes
- On study creation:
  - ignore client owner fields
  - set `owner_user_id = authenticated_user.id`
- On study read/update/run/upload routes:
  - require `study.owner_user_id == authenticated_user.id` unless role is `admin`
- Ensure jobs, assets, previews, runs, and interview flows are only reachable through the owning study or admin

**Frontend**
- Stop sending `owner_user_id` from the client entirely
- `/api/backend/*` proxy adds trusted headers:
  - `X-Authenticated-User-Id`
  - `X-Authenticated-User-Role`
  - optionally `X-Authenticated-User-Email`
- Backend trusts these headers only when the deployment shared secret is valid

#### 3. Brute-force protection
Implement the smallest credible anti-abuse controls.

**Must-have in code**
- `auth_login_attempts` table keyed by:
  - normalized email
  - IP
  - rolling window timestamp
- Login rules:
  - lock after **5 failed attempts in 15 minutes**
  - block for **30 minutes**
  - return generic invalid-credentials message
  - do not reveal whether email exists

**Must-have at the edge**
- Add platform/ingress rule for `/login` and auth endpoints:
  - cap unauthenticated requests per IP
  - recommended starting point: **10 requests/min/IP**
- This is required for public launch because app-level login lockouts alone are not enough against distributed probing

#### 4. Usage/cost safeguards
Implement minimal app-level quotas for expensive operations.

**Backend**
- Add `user_usage_counters` table with daily buckets per user and operation
- Track at minimum:
  - `study_create`
  - `survey_upload`
  - `product_image_analysis`
  - `simulation_run`
  - `stability_check`
  - `interview_run`
- Enforce conservative defaults via env:
  - `DAILY_STUDY_CREATE_LIMIT=20`
  - `DAILY_UPLOAD_LIMIT=50`
  - `DAILY_PROVIDER_RUN_LIMIT=20`
- Also enforce:
  - only **one provider-backed run in flight per user** at a time
- Return clear `429` / quota-exceeded errors

**Why this slice is enough**
- It prevents anonymous usage
- It ties activity to a user
- It stops one user from running unbounded provider-backed operations
- It does not require billing, orgs, password reset, or full entitlement systems yet

#### 5. Tests for the first slice
Add/require:
- login success / failure / disabled user
- login lockout after repeated failures
- session expiration / logout
- unauthenticated route rejection
- study creation assigns authenticated owner
- non-owner cannot read/update another user’s study
- admin can access cross-user studies
- provider-backed operations reject after quota exceeded
- proxy forwards authenticated user headers only when session is valid
- build/start fail if auth env is missing in production-like environments

### D. Migration steps from shared-password gate
Use a safe staged migration rather than a hard flip.

1. **Introduce user auth behind the existing deployment secret**
   - backend remains secret-protected
   - public app still reachable only via current gate during development/staging

2. **Add users + sessions + ownership enforcement**
   - bootstrap first admin account
   - verify admin can create/login/use the app
   - verify studies created in this phase are correctly owned

3. **Switch the frontend gate**
   - replace `APP_ACCESS_PASSWORD` flow with real `/login`
   - keep `APP_ACCESS_PASSWORD` as an optional emergency/maintenance extra layer, not the primary auth path

4. **Backfill existing data**
   - assign current existing studies to the bootstrap admin account
   - script/migration:
     - any `studies.owner_user_id IS NULL` -> bootstrap admin user
   - no unowned studies should remain before public launch

5. **Turn on quotas + login throttling**
   - app-level lockout logic active
   - edge rate limits configured
   - provider-backed endpoints reject over-quota usage

6. **Launch in invite-only mode**
   - admin creates users manually
   - no public signup exposed
   - password reset remains manual/admin-assisted for first launch

### E. Final recommendation
**Recommended path to “READY FOR REAL PUBLIC DEPLOYMENT”:**
- **Must-have before public launch**
  - invite-only local accounts
  - signed session cookie
  - study ownership enforcement
  - login brute-force protection
  - daily per-user provider usage limits
  - edge rate limits on login/auth paths
  - backfill all existing studies to a real owner

- **Can follow after launch**
  - self-serve signup
  - password reset email flow
  - MFA
  - organization/team support
  - audit logs
  - billing/plan-based quotas
  - richer admin UI

**Recommendation**
- Do **not** take the app public with only the shared password gate.
- The smallest safe public-launch version is:
  - **invite-only app-owned auth**
  - **per-user study ownership**
  - **login throttling**
  - **daily cost quotas**
  - **edge rate limiting**
- That is the minimal slice that meaningfully changes the risk profile from “controlled deployment” to “real public deployment candidate.”
