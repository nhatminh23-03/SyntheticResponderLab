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

## 1b. Target branch moved — 20 Aug

The QA fixes were built on `2691642`. `yaza_Aug_work` has since advanced **eight commits** to
`d340d14d12ce15ae3c789cbd18f92ad6ee3f9db7`. Two of them land on the same functions this pass changed,
so the fixes cannot be evaluated against `2691642` any more.

| SHA | Commit | Files touched |
|---|---|---|
| `b3bd4b5` | Ground persona generation in real ACS data and fix live-answer fallbacks | `Dockerfile`, `legacy_runtime/backend/simulation/run_manager.py`, **4 × `legacy_runtime/data/processed/priors/*.parquet`**, `scripts/build_grounding_priors.py`, `src/adapters/legacy_backend/domain.py`, `src/api/errors.py`, `tests/conftest.py`, `tests/test_answer_coercion.py`, `tests/test_grounding_priors.py`, `tests/test_studies_endpoints.py` |
| `1c99e92` | Run respondent requests in parallel and default sample size to 20 | `README.md`, `.env.example`, `domain.py`, `src/config/settings.py`, `src/services/study_service.py`, `tests/test_live_run_concurrency.py`, `tests/test_studies_endpoints.py`, `experiment-section.tsx`, `render.yaml` |
| `ff9e36f` | Fix light-mode Analysis contrast and add a coffee demo preset | `.gitignore`, `README.md`, **`legacy_runtime/Provided Info/Cortado Roasters — Coffee Subscription Survey.md`**, `domain.py`, `src/api/studies.py`, `study_service.py`, `tests/test_demo_presets.py`, `globals.css`, `analysis-section.tsx`, `study-mode-section.tsx`, `api.ts` |
| `c58ca44` | Remove the coffee preset card from Study Setup | `README.md`, `study-mode-section.tsx` |
| `724cc68` | Replace the ownership toggles with a single three-way selector | `audience-section.tsx`, `setup-flow-utils.ts`, `tests/setup-flow.test.ts` |
| `c3c10f6` | Add AI survey generation, clipboard image paste, and fix opaque image errors | `README.md`, `domain.py`, `src/api/errors.py`, `studies.py`, `src/schemas/study.py`, `study_service.py`, **`src/services/usage_limits.py`**, `tests/test_answer_coercion.py`, `tests/test_studies_endpoints.py`, `tests/test_survey_generation.py`, `product-section.tsx`, `survey-generator-panel.tsx`, `survey-section.tsx`, `api.ts` |
| `d1ed170` | Add handoff and merge runbook for the `yaza_Aug_work` branch | `Documentation/handoff-2026-08-20.md` |
| `d340d14` | Ignore local `.claude/` agent config | `.gitignore` |

**Overlapping pair:** `b3bd4b5` and `1c99e92`. Both rewrite `_generate_live_response_records_with_debug`
and the fallback paths that F-04, F-04b and the fallback-provenance fix also change.

**Medium risk:** `c3c10f6` touches `usage_limits.py` (F-11's file, different region) and `api.ts`
(F-04/F-07 also change it); `ff9e36f` touches `analysis-section.tsx` and `domain.py`.

`ff9e36f` also adds a **Cortado Roasters coffee-subscription survey preset** to the vendored runtime —
a non-Neo survey shipped in-repo, which is exactly the fixture the F-06 generalization checks need.

### Composition table

Established by reading all eight commits against the eleven fixes, before any code was moved.

| Area | Teammate behaviour (`d340d14`) | Our fix behaviour (`19dd733`) | Desired combined behaviour | Conflict risk |
|---|---|---|---|---|
| **F-01 canonical legacy runtime** | Dockerfile still reconstructs `/app/NeoSmart-Hackathon-App/{backend,Provided Info,data}`; asserts a prior parquet exists in it | Reconstruction removed; `LEGACY_APP_ROOT=./legacy_runtime`; `render.yaml` retargeted | One tree, no reconstruction; **keep the parquet existence guard**, retargeted at `legacy_runtime/data/processed/priors/` | **High** — textual + semantic |
| **Persona grounding** | Four ACS `.parquet` under `legacy_runtime/data/processed/priors/`; builder at `apps/api/scripts/build_grounding_priors.py` | F-01 vendored a `scripts/` tree into `legacy_runtime` | Priors load **because** F-01 points local dev at `legacy_runtime`; the two `scripts/` locations must be reconciled to one | **High** |
| **F-04 coercion fallback** | `_match_survey_option`: exact → normalized → unambiguous containment | Rows carry `is_fallback`; fallbacks excluded from analysis | Complementary — fewer fabrications occur, and whatever still falls back stays labelled and excluded | Medium — expected counts shift |
| **F-04b provider/model failure** | Dispatches **all** calls through a ThreadPoolExecutor before inspecting any result | Raises `ProviderUnavailableApiError` on 400/402/404 in the fold loop | Consume futures as they complete; on a non-retryable status shut down with `cancel_futures=True` and raise. Caps wasted calls at `max_concurrency` instead of the whole run | **High** — semantic |
| **Fallback provenance** | — | `record_is_fallback` parallel list; 3-tuple return | Preserve, re-threaded through the rewritten loop | **High** — same function rewritten by both |
| **Fallback exclusion from analysis** | — | `_split_live_and_fallback_records`, `answer_sourcing` | Unchanged | Low |
| **Model validation** | `serializable_validation_errors`; catalog `google/gemini-2.0-flash-001` → `anthropic/claude-sonnet-4.5` | F-04b references the retired id in error text only | Take theirs — **this closes F-09** | Low |
| **Concurrency** | `SIMULATION_MAX_CONCURRENCY` default 8; results folded in respondent order | Serial loop | Theirs, plus the fail-fast abort above | **High** |
| **Docker packaging** | Copies `legacy_runtime/data` into the reconstructed tree | Asserts `legacy_runtime/backend` | Single tree + parquet guard | **High** |
| **Test fixtures** | `_env_file=None`, `DEPLOYMENT_SHARED_SECRET=None`, `LEGACY_APP_ROOT=API_ROOT/"legacy_runtime"`; skips the docx test if the fixture is absent | Same root via `WORKSPACE_ROOT`; vendored the docx so it is never absent | Their kwargs and `API_ROOT`-relative path; the skip becomes unreachable but harmless | Medium |

### Two contradictions that must not be settled by preferring a branch

1. **`realism_scorecard`.** `b3bd4b5` changed the assertion to `available is False`, on the stated grounds
   that the benchmark file *"does not ship in the vendored legacy runtime yet."* **F-01 ships it.** The
   premise is false after the merge, so the combined tree must assert `True` and the comment must go.
2. **Fail-fast versus parallel dispatch.** Whichever side git leaves behind, the other's intent is silently
   discarded: either a bad model id costs the full N×M provider calls, or the parallelism is reverted.

### Possibly closed upstream — to be confirmed with fresh evidence, not inspection

- **F-02** — the non-hermetic test was rewritten to monkeypatch the scraper, and `conftest` now sets
  `_env_file=None`, which addresses both the regression and the network dependency.
- **F-09** — the retired model is gone from the catalog.
- **§6 persona grounding** — the prior tables now exist. Existing is not loading; see §6 and the
  post-merge verification.

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

The middle column is the finding as recorded on the target SHA. The right column is where each stands on
the release candidate `c64c797` — the table was being read as a standing list long after most of it had
moved.

| Capability | At the target SHA | On `c64c797` |
|---|---|---|
| Fallback synthesis + live/fallback accounting | Yes | Yes, extended — per-row provenance and exclusion |
| Mirror N×M record count | Yes — **but the same test asserted `total_generated_responses == 2`, codifying the wrong count** | **Closed** (`681dc4a`); parameterized across all three modes (`231f9c2`) |
| Insights on a non-Neo survey | **No — largest gap** | **Closed** — `test_neo_metric_gating.py` (`71bbf3b`) |
| PDF survey parsing | **No** | **Closed** — `test_pdf_survey_support.py`, 16 tests (`c3219b7`) |
| Stability check (real repeat loop) | **No** — fully stubbed | **Closed** — `test_stability_check_loop.py` (`231f9c2`) |
| Google Vision real path | **No** — fully monkeypatched | Still monkeypatched; provenance is now asserted (`c64c797`) |
| Alembic migrations | **No** | Target resolution covered (`bcb4626`); the migrations themselves still are not run in tests |
| Postgres, React components, Next.js proxy route | **No** | **Still not covered** |

Backend went from 65 tests to **235**, frontend from 36 to **67**.

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

> **Closed, verified on the combined tree `f048fdd` (20 Aug).** Evidence below in §6b. The finding as
> originally written is kept unchanged for the record.

### 6b. Grounding after the merge — verified, not inferred from file presence

`b3bd4b5` committed the four ACS prior tables. Files existing is not files loading, so each claim was
probed separately, and the prior-loading probe was run in **separate processes per root** — `load_module`
caches by module name, so a single process reports whichever root it saw first.

**The tables only load because F-01 landed.** Same code, two roots:

```
legacy_runtime  (canonical after F-01)
  priors dir              : True (4 parquet)
  grounded_priors_available(): True
  load_grounding_priors() : ['age_income', 'household_size', 'ownership_home_type', 'work_mode']

NeoSmart-Hackathon-App  (where apps/api/.env pointed before this pass)
  priors dir              : False (0 parquet)
  grounded_priors_available(): False
  load_grounding_priors() -> FileNotFoundError: Missing prior file: .../data/processed/priors/...
```

The two fixes are load-bearing for each other: the prior tables live inside `legacy_runtime`, so without
F-01 a local checkout keeps resolving the engine from the nested checkout and grounding stays off — while
reporting success, exactly as before. **A local `apps/api/.env` carrying the old absolute path silently
reintroduces the original defect**; it is untracked, so it survives a branch switch. It must read
`LEGACY_APP_ROOT=./legacy_runtime`.

**Preview and Run now agree.** The original finding was that they took different paths — the UI hardcodes
`use_grounded_priors: true` while the run passed the availability flag, so the run took the silent
`heuristic_only` branch and emitted no warning. On `f048fdd`, live, Neo preset:

| Surface | `persona_generation_mode` |
|---|---|
| `POST /studies/{id}/personas/preview` | `grounded_priors` |
| `POST /studies/{id}/simulation-runs` → `result` | `grounded_priors` |

Preview `prior_notes` name the resolved files, e.g.
`.../apps/api/legacy_runtime/data/processed/priors/age_income_priors.parquet`.
No grounding warning is emitted, which is now correct rather than silent.

`/api/v1/health` reports `grounding_priors: ok`. Overall status is `degraded` for two optional
integrations only — `google_vision` (no credentials) and `hud_lookups` (no token).

**Residual gap:** `cex_affordability_available` is still **False**. `b3bd4b5` built four tables; the CEX
affordability priors are not among them, so that half of the grounding story remains unbuilt. The
`build_cex_affordability_priors.py` stage vendored by F-01 is what would produce it.

---



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
