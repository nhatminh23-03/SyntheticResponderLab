# 00 — QA Baseline

**Pass:** Classroom-readiness QA · **Date:** 2026-08-17
**Scope:** static + API-level verification (browser E2E recorded separately in 02/03).
**Rule applied:** every statement below is runtime-verified or source-verified. Superseded speculation has been removed.

---

## 1. Target under test

| Item | Value |
|---|---|
| Target branch | `yaza_Aug_work` |
| **Target SHA** | `7645dfa25412166fb4d6bd6e3f881e5ef926dc69` |
| Target commit | "Refine setup workflow and product autofill" — Yaza Myo Tun, 2026-08-17 |
| Comparison baseline | `main` @ `1cc5ace93ec41240915cbd7e843b014f42d132b4` (2026-04-30) |
| Relationship | `yaza_Aug_work` = `main` + **exactly one commit**; parent of `7645dfa` is `1cc5ace` |
| Verification method | `git ls-remote` + GitHub API (read-only), then a detached worktree at `7645dfa` |

### Corrections to the original handoff brief
- `Yaza_Final_Update` @ `86563a8` (2026-04-26) is **superseded**, not newer. It contains **zero** files absent from `main`.
- `main` is the newer baseline; it adds Render deploy fixes, the vendored legacy runtime, bundled Neo presets, and logo branding.
- The working copy checked out at session start was `main`, and was **~3.5 months stale** — `yaza_Aug_work` was not fetched locally.
- An unreviewed `vercel/vercel-web-analytics-integrati-e72du0` branch also exists on the remote.

### What the teammate commit changes
194 additions / 33 deletions across 10 files.

| File | Change |
|---|---|
| `apps/api/src/adapters/legacy_backend/domain.py` | +127 — no-LLM regex fallback for `product_url_autofill` |
| `apps/api/src/services/health_service.py` | +27 — new `database_schema` hard-fail check |
| `apps/api/tests/test_health.py` | +14 — first new test |
| `apps/web/src/lib/utils.ts` | `formatSectionIndex`: `index+1` → `String(index)` |
| `apps/web/src/components/ui/section-header.tsx` | merges two chips into "01. Study Setup" |
| `apps/web/src/components/sections/study-mode-section.tsx` | **deletes** the hardcoded `Step 1 of 6` chip |
| `apps/web/src/components/sections/main-hero-section.tsx` | **removes** the duplicate "See Workflow" button |
| `apps/web/src/components/sections/audience-section.tsx` | "Income" → "Household Income"; "Metro" → "City or Area" |
| `apps/web/src/components/ui/workflow-nav.tsx` | nav grid `grid-cols-10`, tighter type scale |
| `apps/web/package-lock.json` | dependency bump |

---

## 2. Runtime pinned for QA

Production base image is `python:3.11-slim`, so QA pinned **Python 3.11.15** and built a clean venv via `pip install -e ".[dev]"` — the same resolution path the Docker build uses.

| Package | Resolved |
|---|---|
| python | 3.11.15 |
| pandas | 3.0.5 |
| starlette | 1.6.0 |
| fastapi | 0.141.1 |
| sqlalchemy | 2.0.52 |
| pytest | 9.1.1 |

**Environment hazard:** the repo contains two pre-existing, divergent virtualenvs — `apps/api/.venv` (Python 3.9.6 / pandas 2.3.3 / starlette 0.49.3) and the root `.venv` (Python 3.11.15 / pandas 3.0.2 / starlette 1.0.0). `__pycache__` artifacts show the **root** venv last ran the suite. Dependencies are declared as unpinned floors (`pandas>=2.2`), so each Render rebuild can resolve a different major version. Pin one interpreter before trusting any test result.

---

## 3. Test suites at the target SHA

### Backend — `apps/api/tests`, 65 tests in 8 files
Command: `cd apps/api && pytest -q`

```
main  1cc5ace  →  64 passed
yaza  7645dfa  →  1 failed, 64 passed
```

The single failure is **F-02**, a regression introduced by the target commit.

- No test contacts a live LLM. Two mocking tiers: `test_legacy_live_simulation.py` fakes `llm_client.requests.post` (and therefore exercises real prompt building, parsing, fallback synthesis, record assembly); `test_studies_endpoints.py` / `test_usage_limits.py` stub `execute_simulation_run` wholesale.
- Test DB is built with `Base.metadata.create_all()` — **alembic migrations are never exercised**.
- `pyproject.toml` has no markers, no coverage config, no `addopts`.

### Frontend — `apps/web/tests`, 36 tests in 7 files
Command: `cd apps/web && npm run test:unit` → **36 passed, 0 failed**

Runner is Node's built-in `node:test`. All are pure-function unit tests — no rendering, no DOM, no Playwright. There is **no `lint` and no `typecheck` script**.

### Verified coverage gaps
| Capability | Covered |
|---|---|
| Fallback synthesis + live/fallback accounting | Yes |
| Mirror N×M record count | Yes — **but the same test asserts `total_generated_responses == 2`, codifying the wrong count as expected** |
| Insights on a non-Neo survey | **No — largest gap** |
| PDF survey parsing | **No** |
| Stability check (real repeat loop) | **No** — fully stubbed |
| Google Vision real path | **No** — fully monkeypatched |
| Alembic migrations, Postgres, React components, Next.js proxy route | **No** |

Two further test hazards: `test_upload_aytm_docx_succeeds_with_fallback_parser` reads a `.docx` that is **not vendored** into `legacy_runtime` (so it cannot pass in Docker/CI), and after F-02 the suite makes **real outbound HTTP requests**.

---

## 4. Architecture

Monorepo, three code trees:

- **`apps/web`** — Next.js 14 + Tailwind + Framer Motion. Single-page workflow (`apps/web/src/app/page.tsx`), one component per stage under `components/sections/`. Stage list in `lib/workflow-sections.ts`: 13 entries = Main + 9 primary stages + 3 interview screens, of which Research Brief and Interview Insights are grouped under the Interview tab → **10 nav items**.
- **`apps/api`** — FastAPI + SQLAlchemy + Alembic. `src/adapters/legacy_backend/domain.py` wraps the legacy engine **and** derives all Result/Insight data.
- **Legacy simulation engine** — 56 Python modules, present **twice**: `NeoSmart-Hackathon-App/backend/` (used locally) and `apps/api/legacy_runtime/backend/` (used in production). Verified **byte-identical** at this SHA (`diff -rq`, only `__pycache__` differs), with nothing enforcing that.

Module resolution: `src/adapters/legacy_backend/runtime.py` inserts `LEGACY_APP_ROOT` onto `sys.path` and imports everything as `backend.*`. **Local and production therefore execute different copies of the same code.**

The entire run executes **synchronously inside the HTTP request**; the `Job` table is only a result envelope, and the animated progress bar is a local animation, not a job stream.

**There is no responses table.** `src/persistence/models.py` defines `Study`, `StudyAsset`, `StudySectionState`, `StudyProductEnrichment`, `PersonaPreviewRun`, `PersonaPreviewPersona`, `Job`, `UserUsageCounter`. An entire run — every record, persona, warning — is one JSON blob in `jobs.result_json`, re-parsed into a pandas DataFrame on every analysis request.

---

## 5. Reproducibility defect (verified live)

`NeoSmart-Hackathon-App` is recorded as a **gitlink, mode `160000`**, at commit `0d066c1`, pointing at **`https://github.com/ytun1/NeoSmart-Hackathon-App.git` — a different owner's repository**. There is **no `.gitmodules` file**.

Verified: `git worktree add` of either commit produced an **empty** directory at that path. `git submodule update --init` cannot work because there is no submodule mapping to read.

`apps/api/.env` points `LEGACY_APP_ROOT` there, and every simulation/persona/analysis call loads `backend.*` from it. A new contributor cloning the repo gets a non-running application. Recorded as **F-01**.

**There is no LICENSE or COPYING file tracked anywhere in the repository** — this blocks the CARLE open-repository deposit, and is compounded by part of the runtime living in a third-party repo.

---

## 6. Persona grounding — verified, not inferred

Runtime probe at the target SHA:

```
grounded_priors_available()       : False
cex_affordability_priors_avail()  : False
priors_dir resolved to            : <legacy_root>/data/processed/priors
priors_dir exists                 : False

use_grounded_priors=True   -> mode='heuristic_fallback'
use_grounded_priors=False  -> mode='heuristic_only'
```

- `prior_sampler.load_grounding_priors()` expects 10 `.parquet` tables. **No `.parquet` file exists anywhere in the repository.**
- `legacy_runtime/backend/grounding/priors.py` is a stub: `"""Grounding priors placeholder."""  # TODO`.
- `apps/api/Dockerfile` copies only `backend/` and `Provided Info/` into `/app/NeoSmart-Hackathon-App/` — it **never creates `data/`**, so the deployed container cannot load priors either.
- `domain.py:697` passes `use_grounded_priors=grounded_priors_available` (False) → the run takes the **`heuristic_only`** branch. The warning at `domain.py:762` fires **only** on `heuristic_fallback`, so **a real run emits no grounding warning at all**.
- The persona *preview* hardcodes `use_grounded_priors: true` (`experiment-section.tsx:385`) → `heuristic_fallback` → does warn. **Preview and Run take different code paths.**
- The `/health` endpoint does report `grounding_priors: warn — "Grounding prior files missing; persona preview will degrade."` (message understates: the *run* degrades too).

**Conclusion:** every persona generated locally or in production today is rule-based. Personas must not be described as census-grounded. Rebuilding priors requires downloading ACS/PUMS, AHS and CEX data via `NeoSmart-Hackathon-App/scripts/download_*.sh` and running the `build_grounding_priors*.py` pipeline.

---

## 7. Real-panel benchmark status

**No real 600-person panel dataset exists in the codebase.** The only benchmark artifact is
`NeoSmart-Hackathon-App/data/processed/benchmarks/realism_targets_neo_smart_template.json` — a **two-question template** whose own notes read *"Replace with real observed distribution from survey summary."*

`analysis/realism.py` is a generic scorer but is gated to Neo only (`domain.py:2156`), its targets file is absent from the vendored tree used in Docker, and **no frontend component reads `realism_scorecard`**.

The plan step "benchmark against the panel of 600" (due 31 Aug) has no implementation behind it.

---

## 8. Environment and external dependencies

| Service | Env var(s) | Required | Behaviour when missing |
|---|---|---|---|
| OpenRouter | `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` | optional (degrades health) | **run still "completes" via deterministic fallback — the core QA trap** |
| Google Cloud Vision | `GOOGLE_CLOUD_API_KEY` / `..._SERVICE_ACCOUNT_JSON` / `..._SERVICE_ACCOUNT_PATH` | optional | `503` on image analysis |
| Database | `DATABASE_URL` | **required, no default** | pydantic validation error at import; health hard-fail |
| Legacy engine | `LEGACY_APP_ROOT` | **required** | health hard-fail; nothing can run |
| Artifacts | `ARTIFACTS_ROOT` | **required**, writable | health hard-fail |
| Deployment gate | `DEPLOYMENT_SHARED_SECRET` | required outside dev, ≥16 chars | health hard-fail in prod |
| Clerk (frontend) | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | required in prod unless `APP_ACCESS_PASSWORD` set | build/startup assertion throws |
| HUD | `HUD_API_TOKEN` | optional | geography enrichment degrades |
| Anthropic | `ANTHROPIC_API_KEY` | declared, **no active code path** | no-op |

**Deployment topology:** Browser → Vercel (`apps/web`, root dir `apps/web`) → Next.js server proxy `/api/backend/*` → Render Docker service (`apps/api`) → Postgres, with a 10 GB disk at `/var/data` for `ARTIFACTS_ROOT`. Backend: `https://synthetic-responder-api.onrender.com`. `alembic upgrade head` runs at **container start**. Quotas: 20 study creations/day, 50 uploads/day, 20 provider runs/day per user, one provider run in flight.

**Local-setup defect (F-03):** `apps/api/alembic/env.py` reads only `os.getenv("DATABASE_URL")` and does **not** load `.env`, while `AppSettings` does. Following the README migrates `alembic.ini`'s fallback `sqlite:///./local-dev.db` and leaves the app's real database empty. Masked in production because `render.yaml` sets a true env var.

**Frontend env conflict:** `apps/web/.env.local` sets `APP_ACCESS_PASSWORD` and omits Clerk keys while `apps/web/.env` has Clerk keys. `.env.local` wins, so a local `next dev` runs in **legacy shared-password gate mode**.

**Provider account state at time of QA:** OpenRouter credits were exhausted (balance −$0.1998) at the start of the pass; credits were added mid-pass, after which the live path was verified successfully. See **F-04 / F-04b**.

---

## 9. Verified-working baseline

Recorded so the defect list is not read as "nothing works":

- **The live survey pipeline is genuine.** Mirror N=3 with two valid models → `live_answer_rate = 1.0`, 18/18 truly live, 0 fallback, 0 provider errors, 0 warnings, with distinct in-character answers.
- **Experiment-mode allocation is correct** at record level in all three modes (see `04_Experiment_Mode_Verification.md`).
- **Markdown and DOCX survey parsing work** — 32 and 39 questions respectively, correct types, matrix expansion, transparent warnings.
- **The new `database_schema` health check works** and caught a real environment misconfiguration on first use.
- **Custom-study interviews are genuinely live** (real dual-model + judge calls).
- **No NaN, no crash, no divide-by-zero** was produced by any Insights path tested, including non-Neo surveys.
