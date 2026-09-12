# /interview: run the AI-to-AI batch, and regenerate a cached answer

Two gaps on `apps/web/src/app/interview/page.tsx`, both found live on 2026-09-10.

## Decision already made

The batch uses the page's own fixed 30 personas and the research brief that is already
hardcoded for this page. It does **not** read study section state (Audience, Product, Market,
Survey tabs) and does **not** require a persona-preview run. Anderson's call, 2026-09-10: "lets
ignore the workflow state." Rationale: students never see those tabs, there are zero
persona-preview rows in the database, and `scripts/prerecord_interviews.py` already runs
headlessly off the same fixed personas and brief.

## Outcome 1 — a student can run the AI-to-AI batch from /interview

Today `personaCount` feeds only the pre-flight cost estimate. There is no run control and no
call to any batch endpoint.

- A run control sits with the batch slider and starts a run of `personaCount` personas using the
  selected interviewer and interviewee models.
- Progress is visible while it runs, and the finished transcripts are readable without a reload.
- Measured cost is shown when it finishes, next to the pre-flight estimate it was compared
  against.
- The existing budget caps still stop the run: `RUN_BUDGET_USD` per session, `CLASS_BUDGET_USD`
  per cohort, and `NEO_LLM_BUDGET_USD` when set. A budget stop surfaces in the UI as a budget
  stop, not as a generic error.
- Expensive models stay behind the existing opt-in checkbox.
- Cache-first behaviour is unchanged, so re-running the same personas and questions replays free.

Do not reuse `start_interview_run` as it stands: it resolves personas from the latest
persona-preview run and reads `product` and `audience` section rows. Either give it a
fixed-persona path that skips both, or add a sibling entry point. Whichever is chosen, the
existing workflow-driven callers must keep working unchanged.

## Outcome 2 — a regenerate control on a cached answer

Identical persona + model + question + history returns the stored answer verbatim. Correct, and
it is what makes classroom replay free, but with no way to force a fresh call it reads as a
frozen UI.

- A regenerate control on an answer requests a new response instead of the cached one.
- Only that one call bypasses the cache. The global cache mode is untouched for everyone else.
- The fresh answer is cached in turn, so the next identical request replays free again.
- Regenerating is a paid call and is subject to the same budget caps.

`CACHE_OFF` already exists in `interview_cache.py`; today every call site passes
`settings.cache_mode`, so the work is threading a per-request override through the chat and
compare paths.

## Checks

- `apps/api/.venv/bin/python -m pytest apps/api/tests -q` passes.
- A test drives the batch entry point with a stubbed provider and asserts it needs no
  persona-preview run and no section rows.
- A test asserts a budget stop during a batch surfaces as a quota error, not a generic failure.
- A test asserts the regenerate path calls the provider on a question whose answer is already
  cached, and that a normal request for that same question still replays from cache afterwards.

## Do not touch

- `scripts/prerecord_interviews.py` and its tests.
- The existing workflow-driven interview run used by the main page.
- Budget constants in `src/services/llm_budget.py`.
- `docs/cost-report.md` and `apps/api/tests/test_cost_report.py`.
