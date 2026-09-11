# Batch and regeneration handoff

Implemented in the current uncommitted diff on top of `91b6e56` (prior commits: `61b9424`, `2068be9`, `617eab8`, `2398890`). Preserve the pre-existing modified `DONE.md` and untracked wrapper `build.sh`. This session added check commands to the Sol outcomes in `DONE.md`; it did not mark the outcomes complete or write to the wrapper-owned board.

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
