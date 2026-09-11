# Lin classroom feedback — implementation handoff

Implemented on `4dd304e` (following batch merge `d965506` and cleanup `a084941`).
No commits or board writes were made. The wrapper owns board posts and checkboxes.
Preserved the pre-existing DONE additions and untracked `build.sh`.

Changes:
- `apps/api/src/services/standalone_themes.py` and owned GET/POST routes in
  `apps/api/src/api/studies.py`: completed-batch themes, explicit paid authorization,
  transcript-content revision, cached result, serialized duplicate requests,
  versioned explicit retries, grounded quote validation and safe diagnostic metadata.
  Read requests never generate. Extraction usage enters the existing InterviewTurn
  ledger as an empty-text accounting row and contributes to run/class limits.
- `apps/api/src/services/interview_service.py`: lifted the existing prompt and
  extraction protocol into shared helpers. Main-workflow model, prompt, cache,
  response and authorization behavior stay the same; its regression passes.
- `apps/web/src/app/interview/page.tsx`: Choose / Interview / Themes steps with
  back navigation and heading focus; native cost confirmations name batch count,
  both models and estimate, including resume/recovery. Comparison is an optional
  disclosure. Themes require a separate confirmation, preserve transcripts on error,
  reject late responses for another run, and link quotes to persona transcripts.
- `apps/web/src/lib/classroom-access.ts`: narrowly allow the classroom themes paths.
- `apps/web/public/prerecorded-interviews.html`: one back link; recording data unchanged.
- Regressions: `apps/api/tests/test_standalone_themes.py` and
  `apps/web/tests/interview-batch-controls.test.ts`.
- DONE now has runnable checks for all 22 outcomes, relative to its own directory;
  wrapper-owned checkbox state is unchanged.

Verification:
- `./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q`: 251 passed,
  10 existing deprecation warnings. Includes 17 new theme cases.
- `cd apps/web && npm run test:unit`: 88 passed.
- `cd apps/web && ./node_modules/.bin/tsc --noEmit --incremental false`: passed.
- `git diff --check`: passed. Budget module/constants, prerecord script, docs cost
  report, and cost-report tests are unchanged against HEAD.
- All seven distinct DONE commands passed when executed verbatim from the plan
  directory; all 22 outcomes now have nonempty machine checks.

The first full API run lacked the local CLI settings and failed two existing
subprocess tests. An ignored, credential-free `apps/api/.env` supplies only test
settings; the full suite then passed. Ignored dependency directories use existing
local packages. Do not commit this machine-local setup.

Limitations / next verification: live browser checking could not run because this
sandbox refused the Next server listen socket (`EPERM`, port 3019). Run keyboard,
confirmation and visual smoke checks in a browser, then PostgreSQL cross-process
concurrency checks in an integration environment. No paid provider calls, live
PostgreSQL checks, or unrelated R checks ran. Native browser confirmation supplies
focus trapping, keyboard acceptance/cancellation and focus restoration. Page tests
exercise the actual React handlers through the existing deterministic harness.
The inherited process-crash window between provider acceptance and DB commit
remains; caught timeouts warn and require explicit retry, with unknown spend never
represented as known zero. Themes are for completed standalone batches; optional
single-question comparison/chat remains an exploration tool.

Dirty files are the implementation/test files above, DONE, this HANDOFF, and the
preserved wrapper `build.sh`. No further implementation patch is identified by the
checks. Do not touch the research pipeline, budget helpers/constants, prerecord
script or cost-report files. There is no repository vault.
