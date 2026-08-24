# Fixed Persona Set Workflow

**Date:** 2026-08-23
**Status:** Implemented and verified. No interview has been run against the selected personas — that step awaits explicit approval.

## Purpose

Dr. Wang's research deliverable: generate ~15 synthetic persona candidates with the application's
current grounded persona-generation pipeline, review them in the browser, select exactly 5, and
persist that selection as a **fixed persona set** that later synthetic interviews reuse verbatim.
Interviews must never silently regenerate personas or drift to a newer preview batch.

### Research isolation constraint

The real 600-participant AYTM dataset, the AYTM report, and the Tony interview/transcript play no
role in candidate generation. This is verified, not assumed:

- The respondent-level dataset and the Tony transcript are not present in the repository at all.
- The AYTM survey docx/report under `Provided Info/` are read only by the survey-questionnaire
  loaders, never by persona generation.
- Candidate generation's entire file read-set is the four Census-ACS-derived parquet prior tables
  in `apps/api/legacy_runtime/data/processed/priors/` (plus optional HUD ZIP lookups when the
  audience specifies a ZIP code).
- A regression test (`test_candidate_generation_never_opens_withheld_research_files`) installs a
  Python audit hook during real grounded generation, selection, and finalization, and fails if any
  file path matching AYTM/Tony/benchmark patterns is opened.

These materials remain untouched for the Aug 29–31 validation, so the synthetic-vs-real
comparison stays independent.

## The workflow

In the app, section **07. Personas** (between Experiment and Run):

1. Save **Audience** and the **Experiment plan** (the persona-preview endpoint requires both).
2. Click **Generate 15 persona candidates**. This calls the existing
   `POST /personas/preview` endpoint with `sample_size: 15` — the current grounded pipeline,
   completely unchanged. The page shows `15 candidates generated`, the generation mode
   (expected: `grounded_priors`), and the batch id (`ppr_…`).
3. The batch is **pinned immediately**: a draft persona set referencing that exact preview run is
   saved. Later previews (including the automatic one triggered by re-saving the experiment plan)
   cannot swap the candidates under review.
4. Review the cards. Each shows only persisted research attributes: persona id, segment, fit
   tier, age bucket, income bucket, ownership + home type, household size, work mode, awareness
   stage, lifestyle tags, likely use case, likely barrier. No invented biographies.
5. Select exactly 5 (`Selected N / 5`; a sixth selection is blocked). Optional reviewer note per
   selected persona. **Save draft selection** persists work-in-progress across reloads.
6. **Save Fixed Persona Set** finalizes. Finalization requires exactly 5, locks the set, and
   disables regeneration and further edits.
7. **Export CSV** downloads the candidate table (available before and after finalization).

## What is guaranteed after finalization

- The five selected `PersonaPreviewPersona` rows are referenced by immutable UUID. Preview rows
  are append-only in this application — nothing ever deletes or rewrites them.
- **Interview runs automatically use the finalized set.** `start_interview_run` resolves personas
  through the set when one is finalized, and falls back to the previous behavior (all personas of
  the latest preview) when none exists. The fallback path is byte-identical to the old behavior.
- Every interview run records its persona provenance: `persona_set_id` (`fps_…`) and
  `preview_run_id` (`ppr_…`) are stamped into the job payload and result.
- Full grounding provenance is reachable through the pinned preview run: generation mode, prior
  availability, per-table prior notes and source paths, geography context, seed, sample size,
  and generation timestamp.

## Data model

Two small tables (Alembic migration `0003_fixed_persona_sets`):

- `fixed_persona_sets` — at most one per study (`study_id` UNIQUE). Columns: `public_id`
  (`fps_…`), `preview_run_id` (FK to the pinned candidate batch, no cascade — provenance must
  survive), `status` (`draft` | `finalized`), `generation_mode` (denormalized audit snapshot),
  `created_at` / `updated_at` / `finalized_at`.
- `fixed_persona_set_members` — the selection. Columns: `preview_persona_id` (FK to the exact
  persona row), `position`, `reviewer_note`. `UNIQUE(set_id, preview_persona_id)` prevents
  double-selection at the schema level.

The migrations-current health sentinel (`_database_schema_check`) now probes
`fixed_persona_sets`; deployments must run `alembic upgrade head` (the Docker CMD already does).

## API

- `GET /api/v1/studies/{study_id}/persona-set` → `{"persona_set": null | PersonaSet}`
- `PATCH /api/v1/studies/{study_id}/persona-set` — upsert the draft:
  `{"preview_run_id": "ppr_…", "selections": [{"candidate_id": "<uuid>", "reviewer_note": "…"?}]}`.
  Rejects: finalized set (409), run not belonging to the study (404), candidate ids from another
  run, unknown ids, duplicates (400).
- `POST /api/v1/studies/{study_id}/persona-set/finalize` — 409 unless the draft holds exactly 5.

The persona-preview serializer now additively exposes `candidate_id` (row UUID) and `row_index`
on every persona — the `PERS_NNN` label restarts at 001 for every batch and must never be used as
a cross-run identifier.

## CSV export

Client-side, whitelist-only columns (nothing else can leak):
`persona_id, segment_label, fit_tier, age_bucket, income_bucket, ownership, home_type,
household_size_bucket, work_mode, likely_use_case, likely_barrier, awareness_stage,
generation_mode, review_status, reviewer_notes` — RFC-4180 quoting, one row per candidate,
`review_status` = `selected` / `not_selected`.

## Verification record (2026-08-23)

- Backend: 244 tests passing, including 9 new persona-set tests covering the full regression
  list (15 grounded candidates persisted; draft round-trip; exactly-5 finalization; selection
  integrity; reload identity; interview uses the pinned set after a newer preview repoints the
  study; no-set fallback unchanged; experiment `sample_size` untouched; withheld-file audit
  guard).
- Frontend: 75 unit tests passing (8 new for selection rules and CSV), `npm run build` and the
  TypeScript check clean.
- Live browser E2E: batch `ppr_2ec4add4a31a` (15 candidates, `grounded_priors`), five selected
  (PERS_001/003/005/007/009), finalized as `fps_ce033baebaf0` with a reviewer note; identical
  five and note after reload; selection locked. Candidate count is independent of the experiment
  `sample_size`.

## Open decisions for Dr. Wang

1. **Unlock/replace:** a finalized set is currently immutable. If a re-selection round is ever
   needed, that is an explicit follow-up change.
2. **Study mode for the real deliverable:** `neo_smart` demo mode returns seeded fixture
   interviews; live interviews require a "general" (Custom) study. Persona generation is
   identical in both.
3. **Seed:** candidate generation can accept a fixed `seed` for regenerable batches. Not needed
   for reuse (personas are persisted), but available.
4. **Running the interviews** against the five selected personas — explicitly not done yet.
