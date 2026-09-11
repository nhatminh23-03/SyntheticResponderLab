# DONE — /interview: run the AI-to-AI batch, and regenerate a cached answer

Goal: on `apps/web/src/app/interview/page.tsx` a student can actually run the AI-to-AI batch the
slider sizes, and can force a fresh answer when the cache replays an identical one.

**Decision already made, do not revisit.** The batch uses the page's own fixed 30 personas and the
research brief already hardcoded for this page. It does NOT read study section state (Audience,
Product, Market, Survey) and does NOT require a persona-preview run. Anderson, 2026-09-10: "lets
ignore the workflow state." There are zero `persona_preview_runs` rows in the database, students
never see those tabs, and `scripts/prerecord_interviews.py` already runs headlessly off the same
fixed personas and brief.

Test command for every check below unless stated otherwise:
`cd /Users/andersonedmond/dev/SyntheticResponderLab && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q`

## Outcome 1 — the batch actually runs

- [ ] The batch entry point runs N personas from the page's fixed set with a stubbed provider and needs no persona-preview run and no section rows — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k batch`
- [ ] `personaCount` reaches that entry point instead of only the cost estimator: the page issues a request carrying the slider value and the two selected models — check: `grep -n "personaCount" apps/web/src/app/interview/page.tsx | grep -v preflight`
- [ ] A budget stop during a batch surfaces as a quota error carrying the cap that tripped, not a generic failure — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k budget`
- [ ] Re-running the same personas and questions replays from cache and records zero new cost — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k batch`
- [ ] The run's measured cost is returned to the caller so the page can show it against the pre-flight estimate — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k batch`

## Outcome 2 — regenerate a cached answer

- [ ] A regenerate request calls the provider for a question whose answer is already cached — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`
- [ ] A normal request for that same question still replays from cache afterwards, so the override is per-request and the global cache mode is untouched — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`
- [ ] The regenerated answer is itself cached, so the next identical normal request is free — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`
- [ ] Regenerating is subject to the same budget caps as any paid call — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`

## Nothing already working broke

- [ ] Full API suite passes — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q`
- [ ] The pre-record script is untouched — check: `git diff --quiet HEAD -- scripts/prerecord_interviews.py apps/api/tests/test_prerecord_interviews.py`
- [ ] The cost report and its tests are untouched — check: `git diff --quiet HEAD -- docs/cost-report.md apps/api/tests/test_cost_report.py`
- [ ] Budget constants are unchanged — check: `grep -q 'RUN_BUDGET_USD: Final\[Decimal\] = Decimal("0.75")' apps/api/src/services/llm_budget.py && grep -q 'CLASS_RUN_CAP: Final\[int\] = 30' apps/api/src/services/llm_budget.py`
- [ ] The existing workflow-driven `start_interview_run` still works for the main page — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q`
- [ ] The R analysis suite still passes — check: `/usr/local/bin/Rscript analysis/tests/test_all.R`

## Out of scope

- Changing the global cache mode default.
- Touching the main workflow page or its tabs.
- Re-recording the Qwen interviews whose reasoning leaked into the answer text (separate issue).
- Provider pinning on OpenRouter.
