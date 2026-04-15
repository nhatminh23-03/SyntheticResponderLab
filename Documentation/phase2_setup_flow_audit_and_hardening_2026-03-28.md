# Phase 2: Setup Flow Audit And Hardening

Date: 2026-03-28

## Status

Phase 2 focused on truthfulness, wiring correctness, and end-to-end setup stability for the premium one-page frontend before any Simulation UI work begins.

Scope covered:
- Main
- Study Mode
- Audience
- Product
- Market
- Survey
- Experiment

Explicitly out of scope:
- Simulation / Run UI
- Analysis UI
- Insights UI
- Interview UI

Outcome:
- the setup slice is now backend-wired through Experiment
- persona preview now lives in the Experiment chapter as the final pre-run validation step
- workflow readiness is backend-derived and aligned to the current frontend flow
- the Neo/general persistence issue is now explained correctly and partially hardened in code

## Why This Phase Was Needed

The frontend had reached a strong visual state, but the setup flow was not yet fully trustworthy as a study-driven product workflow.

At the start of this phase, the main risks were:
- visual progression could happen even when canonical study state was incomplete
- Experiment was still local-only and not persisted in the backend
- backend workflow readiness still reflected an older `personas` stage instead of the current one-page flow
- mode-dependent Neo defaults could linger in some sections after switching modes
- users could confuse "same saved study reopened" with "prefills are broken"

The goal of Phase 2 was to make the setup slice function as a real persisted workflow, not a prototype with attractive scroll behavior.

## Baseline Before Phase 2

Before this pass:
- study bootstrap already existed
- study mode, audience, product, market, and survey were mostly backend-wired
- the standalone Personas page had already been removed to match the legacy Streamlit flow
- Neo survey preset loading had already been restored in the new API
- DOCX survey fallback parsing had already been added for AYTM-style exports

But several important gaps remained:
- Experiment Design was still local-only
- workflow readiness still used an outdated backend stage model
- persona preview was not positioned correctly in the new flow
- some UI states still implied more saved progress than the backend had actually confirmed

## Wiring Audit Findings

### 1. Canonical Study Ownership Was Mostly Correct, But Incomplete

The high-level architecture was directionally correct:
- backend owns canonical study state
- frontend owns drafts and unsaved edits
- `StudyProvider` restores a study from local storage or creates one on first entry
- section saves call backend endpoints and rehydrate from `GET /api/v1/studies/{study_id}`

The main missing piece was that `experiment` was not yet part of canonical backend study state.

Impact:
- the final setup chapter was not persisted
- readiness could not truthfully reflect completion of the setup slice
- the app was not actually ready to support a reliable Simulation UI handoff

### 2. The Neo To General “Sticky Prefill” Problem Had Two Different Causes

This issue turned out to be a combination of:

1. a real frontend hydration bug
2. expected persistence behavior that was not clearly explained in the UX

#### The actual bug

The Audience section was rehydrating from saved audience timestamps and status, but not from `study_mode` changes.

That meant:
- if no audience had been saved yet
- and Neo local defaults had been loaded into the Audience draft
- switching to General could leave the Neo draft visible until another audience-related change triggered hydration

#### The expected persistence behavior

Even after fixing the hydration bug, users could still see Neo information after switching back to General because they were still in the same saved study.

The app intentionally restores the active study using:
- browser `localStorage`
- backend persisted study state in `apps/api/local-dev.db`

So when a user:
1. starts a Neo study
2. saves Audience/Product/Market/Survey/Experiment
3. switches the mode to General within the same study

the already-saved downstream sections still exist in canonical backend state. That is not a cache bug by itself; it is the same persisted study being reopened and updated.

### 3. Backend Workflow Readiness Was Outdated

The backend workflow service still used:
- `study_mode`
- `audience`
- `product`
- `market`
- `survey`
- `personas`

But the current intended setup flow is:
- Main
- Study Mode
- Audience
- Product
- Market
- Survey
- Experiment

The old workflow logic also made `ready_for_persona_preview` true too early, effectively after Audience was saved.

Impact:
- setup sections could show misleading “aligned” or “ready” messaging
- the backend contract did not match the frontend chapter structure
- the handoff to future Simulation UI would have been built on a false readiness signal

### 4. Experiment Design Was Not Real Yet

The Experiment section previously:
- loaded continuity context
- validated locally
- displayed premium UI
- but did not persist anything to the backend

It explicitly told the user it was local-only.

That made the setup slice incomplete in a very practical sense:
- no canonical experiment plan
- no truthful workflow completion
- no solid pre-run state to hand into Simulation

### 5. Persona Preview Needed To Live In Experiment

Since the standalone Personas page was removed to match the legacy Streamlit flow, the setup slice still needed a real way to verify the study before Simulation UI exists.

The right place for that is the Experiment chapter:
- after survey is saved
- after execution settings are defined
- before Run / Simulation UI exists

### 6. Frontend Test Coverage Was Too Thin

At the beginning of this pass:
- backend API tests existed
- frontend had no real test harness

That was risky because the core bugs here were not pure rendering problems; they were state and hydration problems.

## Bugs Found

### Bug 1: Audience Neo defaults could survive a mode switch

Root cause:
- Audience hydration did not depend on `study.study_mode.value`

Fix:
- add `study?.study_mode?.value` as a hydration dependency
- centralize section seed resolution logic so mode-dependent prefills are applied consistently

### Bug 2: Experiment was not part of canonical state

Root cause:
- backend `SECTION_KEYS` did not include `experiment`
- no experiment save endpoint existed
- frontend could not rehydrate saved experiment state

Fix:
- add canonical `experiment` section to backend study state
- add experiment save endpoint
- rebuild Experiment chapter to use real backend state

### Bug 3: Workflow model still referenced old `personas` stage

Root cause:
- backend workflow service had not been updated after the frontend flow changed

Fix:
- replace `personas` workflow stage with `experiment`
- compute `ready_for_persona_preview` only when all setup sections are saved
- keep persona preview as a derived capability, not a top-level setup stage

### Bug 4: Study mode switching looked like a reset, but did not communicate preserved saved state

Root cause:
- mode selection UI only confirmed the new mode
- it did not explain that previously saved downstream sections were preserved in the same study

Fix:
- after mode save + study refresh, inspect saved downstream sections
- show explicit messaging that preserved saved setup sections remain attached to the study

### Bug 5: Users had no first-class way to start a truly new study

Root cause:
- the app always tried to restore the last active study from local storage
- there was no explicit “fresh study” action

Fix:
- add `createFreshStudy()` to the provider
- expose `Start Fresh Study` in the Hero section

### Bug 6: Survey stage UI assumed a `ready` status the backend does not emit

Root cause:
- frontend expected a stage status that was not part of the backend workflow contract

Fix:
- align Survey UI to use `complete` vs `in progress`

### Bug 7: Several client saves still surfaced raw error bodies

Root cause:
- some API client methods used plain `response.text()` handling instead of structured API error parsing

Fix:
- standardize client-side error parsing with `readApiErrorMessage()`

### Bug 8: Audience readiness card surfaced only warnings, not hard blockers

Root cause:
- after workflow changes, Experiment blockers now live in `hard_blockers`
- Audience UI only rendered warnings

Fix:
- aggregate both `hard_blockers` and `warnings`

## Backend Changes

### Canonical study model

Added `experiment` as a first-class section in the canonical study model.

Files:
- `apps/api/src/schemas/study.py`
- `apps/api/src/services/study_service.py`

Key effects:
- `CanonicalStudy` now includes `experiment`
- section initialization now creates `experiment` state rows
- study serialization now returns experiment envelope with status, value, timestamps

### Experiment validation and persistence

Added backend support for saving validated experiment plans using the legacy `ExperimentPlan` schema.

Files:
- `apps/api/src/adapters/legacy_backend/domain.py`
- `apps/api/src/services/study_service.py`
- `apps/api/src/api/studies.py`

New capability:
- `PATCH /api/v1/studies/{study_id}/experiment`

Behavior:
- validates against legacy Python schema
- saves canonical experiment section
- updates workflow
- persists across reloads

### Workflow service rewrite

Updated the workflow service so it matches the current setup flow.

File:
- `apps/api/src/services/workflow_service.py`

Changes:
- replaced old `personas` stage with `experiment`
- `experiment` is blocked until all prior setup sections are saved
- `ready_for_persona_preview` now means:
  all setup sections through Experiment are saved

This is much more truthful than the earlier behavior.

### Persona preview gating

Persona preview now requires a saved experiment plan, not just a saved audience.

File:
- `apps/api/src/services/study_service.py`

Effect:
- preview cannot run against an incomplete setup stack
- Experiment now acts as the final canonical setup step before preview

### Model catalog endpoint

Added a backend model catalog endpoint.

Files:
- `apps/api/src/adapters/legacy_backend/domain.py`
- `apps/api/src/services/study_service.py`
- `apps/api/src/api/studies.py`

New endpoint:
- `GET /api/v1/models`

Behavior:
- returns live OpenRouter catalog if available
- returns fallback starter models when provider access is missing
- includes warning text when degraded

## Frontend Changes

### Study bootstrap and fresh-study path

Files:
- `apps/web/src/providers/study-provider.tsx`
- `apps/web/src/components/sections/main-hero-section.tsx`

Changes:
- `StudyProvider` now exposes `createFreshStudy()`
- Hero now includes `Start Fresh Study`

Effect:
- users can intentionally leave a persisted Neo study and start a truly new General study
- this removes confusion between “same study reopened” and “prefill bug”

### Study mode persistence messaging

File:
- `apps/web/src/components/sections/study-mode-section.tsx`

Change:
- after saving study mode, the UI now rehydrates the canonical study
- if downstream sections are already saved, the status message explicitly says they were preserved

Effect:
- the UI no longer implies that changing study mode silently resets the rest of the study

### Shared setup-seeding utilities

Files:
- `apps/web/src/lib/setup-flow-utils.ts`

Added shared utilities for:
- deciding whether a section should use saved state, Neo defaults, or empty state
- generating truthful study mode status messages

Effect:
- reduces drift between sections
- makes mode-dependent prefill behavior more deterministic

### Audience hardening

File:
- `apps/web/src/components/sections/audience-section.tsx`

Changes:
- hydration now reruns when study mode changes
- section seed source now uses shared helper
- readiness card now shows both blockers and warnings for downstream Experiment readiness

Effect:
- the original sticky Neo audience bug is fixed

### Product and Market hardening

Files:
- `apps/web/src/components/sections/product-section.tsx`
- `apps/web/src/components/sections/market-section.tsx`

Changes:
- both now use shared seed-resolution logic
- mode-dependent defaults behave consistently with canonical saved state

Effect:
- unsaved Neo defaults no longer masquerade as saved state
- switching modes is more predictable

### Experiment chapter rebuild

File:
- `apps/web/src/components/sections/experiment-section.tsx`

Major changes:
- load saved experiment state from canonical study
- save experiment plan to backend
- load model catalog from backend
- show truthful readiness based on backend workflow
- generate persona preview from the Experiment chapter
- rehydrate latest saved preview from canonical study state

Effect:
- Experiment is now real
- persona preview now serves as a real final setup check before Simulation UI exists

### API client hardening

File:
- `apps/web/src/lib/api.ts`

Changes:
- added experiment payload/envelope types
- added model catalog types and request helper
- added saveExperiment()
- added generatePersonaPreview()
- standardized structured API error parsing across more endpoints

## Test Coverage Added Or Strengthened

### Backend

File:
- `apps/api/tests/test_studies_endpoints.py`

Added or updated coverage for:
- canonical study includes `experiment`
- workflow is not ready after audience alone
- experiment save endpoint
- persona preview blocked until experiment is saved
- full happy-path preview updates canonical study
- general-mode partial setup rehydrates correctly
- provider-unavailable product URL autofill and image analysis fail clearly
- model catalog fallback works when provider is unavailable

Also updated:
- `apps/api/tests/test_serializer.py`
- `apps/api/tests/conftest.py`

### Frontend

Files:
- `apps/web/tests/setup-flow.test.ts`
- `apps/web/tsconfig.test.json`
- `apps/web/package.json`

Added a lightweight test harness using:
- `tsc`
- Node’s built-in `node:test`

Coverage currently includes:
- saved backend state takes priority over Neo defaults
- Neo defaults only seed unsaved sections
- study mode status message correctly explains preserved sections

Note:
- a richer browser/jsdom-based frontend harness was attempted but not adopted in this environment
- the final frontend harness is dependency-free and intentionally small

## Critical User Journeys Reviewed

### Journey A: Neo happy path

Validated through backend contract tests and frontend wiring review:
- bootstrap study
- select Neo Smart
- save Audience
- save Product
- save Market
- load Neo Survey preset or upload survey
- save Experiment
- generate persona preview
- reload canonical study
- confirm persisted state is rehydrated

Result:
- supported

### Journey B: General path

Validated through automated API coverage:
- create new study in general mode
- save minimal valid Audience + Product
- reload study
- confirm persisted state is correct and next stage is Market

Result:
- supported

### Journey C: degraded / provider-unavailable path

Validated through automated API coverage:
- URL autofill without OpenRouter key
- image analysis without Google Vision credentials
- model catalog fallback when OpenRouter is unavailable
- persona preview still supports degraded grounding behavior via warnings

Result:
- supported with truthful failure/degraded messaging

### Journey D: reload / resume path

Validated through `StudyProvider` review and API tests:
- app restores last active study from local storage
- canonical study is rehydrated from backend
- section values come from backend state, not fake frontend snapshots

Result:
- supported

## Explanation Of The Neo / General Persistence Behavior

This was a key product truthfulness issue, so it deserves a clear explanation.

### What is expected

If a user switches from:
- `neo_smart`
to
- `general`

inside the same study, then any previously saved sections remain saved unless the app explicitly clears them.

That is because:
- the active study id is stored in browser local storage
- the actual study data is persisted in the backend database (`apps/api/local-dev.db` in local dev)

So a reload or dev-server restart does not create a new study. It simply restores the same one.

### What was actually broken

Separately from that expected behavior, the Audience section had a real hydration bug where unsaved Neo defaults could remain visible after a mode switch.

That bug is now fixed.

### What changed in UX

Two UX fixes were added:
- `Start Fresh Study` in Hero
- explicit Study Mode messaging that saved downstream sections were preserved

This makes the system behavior much easier to understand.

## Files Changed In Phase 2

### Backend
- `apps/api/src/schemas/study.py`
- `apps/api/src/adapters/legacy_backend/domain.py`
- `apps/api/src/services/study_service.py`
- `apps/api/src/services/workflow_service.py`
- `apps/api/src/api/studies.py`
- `apps/api/tests/conftest.py`
- `apps/api/tests/test_serializer.py`
- `apps/api/tests/test_studies_endpoints.py`

### Frontend
- `apps/web/src/providers/study-provider.tsx`
- `apps/web/src/components/sections/main-hero-section.tsx`
- `apps/web/src/components/sections/study-mode-section.tsx`
- `apps/web/src/components/sections/audience-section.tsx`
- `apps/web/src/components/sections/product-section.tsx`
- `apps/web/src/components/sections/market-section.tsx`
- `apps/web/src/components/sections/survey-section.tsx`
- `apps/web/src/components/sections/experiment-section.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/setup-flow-utils.ts`
- `apps/web/tests/setup-flow.test.ts`
- `apps/web/tsconfig.test.json`
- `apps/web/package.json`

## Verification Performed

### Backend

Commands run:

```bash
env PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile $(find src tests -name '*.py' | sort)
./.venv/bin/pytest -q
```

Result:
- compile check passed
- `13 passed`

### Frontend

Commands run:

```bash
npm run test:unit
npm run build
```

Result:
- lightweight setup-state unit tests passed
- production build passed

## Remaining Risks

These are not blockers for starting Simulation UI, but they are still real:

### 1. Clear/reset endpoints are still missing

Still not canonical:
- Product clear
- Market clear
- Survey clear
- Experiment clear

Current frontend behavior is honest, but some actions remain local reset patterns instead of backend delete operations.

### 2. Frontend browser-level E2E coverage is still limited

Current frontend coverage is useful, but not full browser automation.

What exists:
- dependency-free regression tests for setup-state logic
- production build validation

What does not exist yet:
- Playwright-style browser E2E
- real DOM interaction coverage for the chapter-navigation flow

### 3. Provider and asset assumptions still matter

Some features still depend on environment and data assets:
- OpenRouter for URL autofill and live model catalog
- Google Vision for image analysis
- grounding priors / lookups for best persona preview quality

These now fail or degrade more clearly, but they still require the right environment to be fully live.

## Go / No-Go Result After Phase 2

Recommendation:
- READY for Simulation UI

Reason:
- the setup flow is now functionally backend-wired through Experiment
- persona preview is available as a real final setup validation step
- canonical study state is respected across setup sections
- reload/resume behavior is real and explainable
- degraded/provider-missing paths fail honestly

Not yet perfect:
- clear endpoints still missing
- browser E2E automation still minimal

But these are not blocking the next phase.

## Recommended Next Step

Proceed to the next phase:
- Simulation / Run UI

Recommended implementation order:
1. define the exact run contract in the Python backend
2. build the Simulation chapter/UI against canonical study + experiment state
3. keep persona preview as the final pre-run checkpoint inside Experiment
4. do not reintroduce a standalone Personas page

## Addendum: Neo Demo Bootstrap And Offline Demo Path

Date: 2026-04-15

This addendum records follow-up changes made after the original Phase 2 pass to support the Neo Smart Living guided demo under live demo time constraints.

### Backend bootstrap for Guided Demo

Files:
- `apps/api/src/services/study_service.py`
- `apps/api/src/api/studies.py`
- `apps/api/tests/test_studies_endpoints.py`

Added capability:
- `POST /api/v1/studies/{study_id}/study-mode/bootstrap/neo`

Behavior:
- saves Neo demo defaults for study mode, audience, product, market, survey, and experiment
- generates and persists persona preview as part of the same bootstrap flow
- seeds a starter research brief so downstream pages are already populated

Effect:
- Guided Demo now prepares a study that is actually ready for Interview Synthesis, instead of only loading local frontend defaults

### Frontend Guided Demo wiring

Files:
- `apps/web/src/components/sections/study-mode-section.tsx`
- `apps/web/src/lib/api.ts`

Changes:
- the Neo Guided Demo action now calls the backend bootstrap endpoint
- status messaging now reflects that the study was prepared for Interview Synthesis

Effect:
- page 02 no longer depends on the user manually saving each setup section before continuing

### Research Brief fallback and autofill

File:
- `apps/web/src/components/sections/research-brief-section.tsx`

Changes:
- when the research brief fetch is empty or fails locally for a Neo study, the section builds a starter brief from saved study context and the latest persona preview

Effect:
- page 12 remains usable in the demo path even when the normal fetch path is degraded locally

### Offline demo interview fixture path

Files:
- `apps/api/src/services/demo_interview_fixtures.py`
- `apps/api/src/services/interview_service.py`
- `apps/api/tests/test_studies_endpoints.py`

Changes:
- Neo studies now use a seeded demo interview run instead of waiting on a live model call
- interview insights are served from cached demo output before any provider-key checks
- reruns for Neo studies return the demo run immediately

Effect:
- the demo no longer depends on OpenRouter latency or availability to show Interview Synthesis and Interview Insights

### Prototype data handling

Files:
- `apps/api/demo_data/prototype/interview_transcripts.csv`
- `apps/api/demo_data/prototype/interview_themes.json`

Changes:
- extracted prototype interview assets are stored directly in the repo under `apps/api/demo_data/prototype/`
- the temporary root zip archive used during implementation was removed after extraction

Effect:
- demo fixtures now load from stable local files without runtime archive handling
