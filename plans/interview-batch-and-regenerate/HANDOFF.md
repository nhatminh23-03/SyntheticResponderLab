# Batch and regeneration handoff

## Current follow-up — regeneration failure and pause checks

Implemented after `6259e2a` in the worktree; no commit created. Recent commits: `6259e2a`, `64d8bd7`, `b254915`. Preserve the pre-existing DONE edits and untracked `archive/build-round2.sh`. The board is wrapper-owned; no board writes were attempted.

- `apps/api/src/services/standalone_interview.py` now commits a consumed answer version on regeneration failure. Queued duplicates receive the stored error; retry requires the new version and `retry: true`. The old transcript and cached answer remain intact. Each accepted attempt has an `interview_regeneration` Job linked to study/owner, answer/turn, session, persona, model and version, with timestamps, outcome and incremental spend. Unknown provider spend is null rather than falsely zero.
- `apps/web/src/lib/standalone-interview.ts` carries retry details from API errors. `apps/web/src/app/interview/page.tsx` retains them for the next explicit chat or comparison regeneration click. Batch pause displays Pausing while awaiting the current call, then Paused after its result and cost arrive. Network errors display execution as unconfirmed.
- Regression evidence is in `apps/api/tests/test_standalone_batch.py` and `apps/web/tests/interview-batch-controls.test.ts`. DONE now includes machine commands for the two previously missing checks; checkbox state remains wrapper-owned.

Verification: full API suite 223 passed (10 deprecation warnings); web unit suite 74 passed; TypeScript `--noEmit --incremental false` passed; R suite nine files passed; protected files match `91b6e56`; workflow `start_interview_run` AST matches baseline; `git diff --check` passed. Initial test run exposed two stale assertions (old retry version and per-request error IDs), corrected before the passing full run.

No live paid calls, browser smoke test, or PostgreSQL integration test performed. Next recommended verification is production-dialect concurrency and browser pause/retry smoke testing. Process crashes between provider acceptance and database commit still require provider reconciliation; this patch addresses caught failures and queued duplicates, not crash recovery. Do not touch prerecorded script/tests, budget constants, cost-report files or the workflow entry point. All changed files listed above plus DONE and this HANDOFF remain uncommitted.

## Current follow-up — four remaining failures

Implemented in the worktree after `b254915` (no new commit). Earlier commits are `5a2dcf0` and `39631a2`; baseline is `91b6e56`. Preserve the pre-existing edits to `DONE.md` and untracked `plans/interview-batch-and-regenerate/archive/`. No board writes were attempted; the wrapper owns posts and checkboxes.

- `standalone_interview.py` consumes a revision even when the provider fails. A failed status requires `retry: true` with the new revision. Old queued submissions return saved status; the page sends retry only after Resume. Progress counts persisted messages rather than attempt revisions.
- Rejected creation requests clear their pending UUID/settings on HTTP 4xx. Network/5xx ambiguity keeps the original UUID for idempotent recovery. Tests cover corrected slider settings and ambiguous recovery.
- An owned GET batches route and classroom proxy rule expose persisted history. The page's Saved batches selector reopens prior completed or paused transcripts and measured costs, including after a later run. Delayed initial recovery cannot replace a newly selected batch.
- Creation consumes the existing interview-run daily quota exactly once, after the idempotency check. The shared quota helper takes the existing PostgreSQL advisory lock to serialize counters, including absent rows. Advances and duplicate creation do not consume quota. Concurrent distinct batch creation and cross-study same-user limits have checks.

Changed application files: `apps/api/src/api/studies.py`, `apps/api/src/services/standalone_interview.py`, `apps/api/src/services/usage_limits.py`, `apps/web/src/app/interview/page.tsx`, `apps/web/src/lib/standalone-interview.ts`, and `apps/web/src/lib/classroom-access.ts`. Regression checks are in the existing API standalone-batch and web batch-controls test files. Added runnable commands to the three previously unchecked DONE outcomes; wrapper-owned checkbox state is preserved.

Verification passed:

- `apps/api/.venv/bin/python -m pytest apps/api/tests -q`: 222 passed, 10 deprecation warnings.
- From `apps/web`: `npm run test:unit`: 73 passed; `./node_modules/.bin/tsc --noEmit --incremental false`: passed.
- `/usr/local/bin/Rscript analysis/tests/test_all.R`: nine files passed.
- Protected-file diff against `91b6e56`: unchanged; exact source comparison of workflow `start_interview_run`: unchanged.
- `git diff --check`: passed.

One web check was initially invoked from the repo root (no package.json); rerunning from `apps/web` passed. No live paid calls, browser smoke test, or running PostgreSQL integration test was performed. SQLite concurrency checks exercise local serialization; production transaction-lock integration remains a next verification step. Provider timeouts can still represent unreported charges, so explicit retry retains its warning. No further functional patch is identified by the local checks. Do not touch prerecorded script/tests, budget constants, cost-report files, or the workflow entry point.

## Round 2 — completion check paths

The implementation is committed in `39631a2`, following pre-build snapshot `91b6e56` and planning commits `61b9424` and `2068be9`. The worktree was clean when round 2 started.

The reported missing Python runner and web directory were caused by check commands resolving relative to `plans/interview-batch-and-regenerate/`. The completion runner explicitly uses the directory containing `DONE.md` as its working directory. Every check now begins with `cd ../..`; the stale machine-specific checkout path in the explanatory text was removed. No application code or wrapper script changed in round 2.

Reverified in this worktree: API suite (218 passed), web unit suite (69 passed), TypeScript type check, and R suite (nine files passed). Protected files, including the whole budget module, match `91b6e56`; the source of workflow-driven `start_interview_run` also matches that commit. No live paid calls or new PostgreSQL/browser integration checks were run; the limitations below still apply.

All 33 corrected check commands were then executed verbatim via subprocesses with the plan directory as their working directory: 33/33 passed. This verifies the command paths without invoking the wrapper or its board operations. `git diff --check` passed.

Only `DONE.md` and this handoff are edited in round 2. Preserve the committed implementation and wrapper `build.sh`. The wrapper owns board posts and completion checkbox updates; no board write was attempted.

## Round 1 implementation record

## Implementation

- `apps/api/src/services/standalone_interview.py`: separate `standalone_batch` jobs, fixed database personas ordered by row index, fixed Tahoe Mini brief, eight adaptive question/answer pairs per persona. Creation is idempotent by request UUID; each advance handles one call with an expected revision. Cache, transcript progress, measured usage, and revision commit together. Status reads expose partial transcripts and failures. Resuming a saved revision does not repeat completed work.
- `apps/api/src/services/interview_service.py`: standalone chat and comparison save original answer request context in `interview_answer` jobs. Session claims enforce study boundaries. Existing PostgreSQL cache/class locks remain in use. A local lock serializes SQLite classroom operations within one development process.
- Regeneration reads server-saved persona, requested model, question, and prior messages, and replaces only the selected persisted answer. Accumulated measured usage remains charged. Expected answer versions deduplicate repeated requests. Chat answers with follow-ups cannot be regenerated. Comparison cards refresh their post-interview score.
- `apps/api/src/services/interview_cache.py`: explicit per-call regeneration skips the read and replaces/inserts the cached answer after provider success. Ordinary `CACHE_OFF`, `cache_first`, and `replay_only` behavior is preserved.
- `apps/api/src/api/studies.py`: owned create/status/advance batch routes and answer regeneration route. No database migration is needed; these use existing Job/InterviewTurn/cache tables.
- `apps/web/src/app/interview/page.tsx`, `src/lib/standalone-interview.ts`, API/comparison types, and classroom allowlist: run/pause/resume, saved batch recovery, transcripts, captured estimate and measured cost, paid regeneration buttons, and activity locks. Only the latest chat answer is regenerable. Failed regeneration leaves its old text and retry version intact.

## Verification

Passed:

- `apps/api/.venv/bin/python -m pytest apps/api/tests -q` — 218 passed.
- `cd apps/web && npm run test:unit` — 69 passed, including actual page handler/render tests with deterministic hooks/transports.
- `cd apps/web && ./node_modules/.bin/tsc --noEmit --incremental false`.
- `/usr/local/bin/Rscript analysis/tests/test_all.R` — nine files passed.
- `git diff --check`.
- Protected-file diff checks and exact source comparison of `start_interview_run` against HEAD.

New API checks live in `apps/api/tests/test_standalone_batch.py` (27 cases). Page interaction checks live in `apps/web/tests/interview-batch-controls.test.ts`. Existing classroom and activity-lock tests were extended.

No live paid provider calls were made. Browser visual verification could not run: the sandbox rejected listening on `127.0.0.1:3019` with `EPERM`. PostgreSQL concurrency was not integration-tested against a running database; concurrent request tests use SQLite, while production uses the existing transaction advisory locks plus row locks.

Local test setup only: ignored `.venv/` and `node_modules/` directories link to installed dependencies in the original checkout. Ignored `apps/api/.env` contains only minimal test settings, no credentials. CLI tests required those basic settings. Do not commit this machine-local setup.

## Recovery and limits

A batch Job's public ID, payload, status, result transcripts/revision, and error persona/model identify progress. Sum InterviewTurn usage for the job ID to inspect its measured spend. The web page saves the latest batch ID and any pending creation request in localStorage, retrieves status, and explicitly resumes from the persisted revision.

Batch and regeneration provider calls use one HTTP attempt. A provider timeout can still mean the provider charged a call whose usage never reached this application; the UI explicitly warns before a manual retry. Completed calls are persisted and not repeated. There is no provider-side idempotency or reconciliation for a process crash between a remote charge and the database commit; measured totals cannot include usage never received. PostgreSQL is required for cross-process production locking; the SQLite helper is for a single local process.

Next verification: run browser smoke tests and PostgreSQL concurrent-request checks outside this sandbox. No further functional patch is planned from the passing local checks. If stronger accounting across lost provider responses is required, add provider-side idempotency/reconciliation rather than silently retrying ambiguous requests.

Do not touch: prerecorded script/tests, cost report/tests, budget constants, or workflow-driven `start_interview_run`. All remain unchanged.
