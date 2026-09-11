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
- [x] The pre-record script is untouched — check: `git diff --quiet HEAD -- scripts/prerecord_interviews.py apps/api/tests/test_prerecord_interviews.py`
- [x] The cost report and its tests are untouched — check: `git diff --quiet HEAD -- docs/cost-report.md apps/api/tests/test_cost_report.py`
- [ ] Budget constants are unchanged — check: `grep -q 'RUN_BUDGET_USD: Final\[Decimal\] = Decimal("0.75")' apps/api/src/services/llm_budget.py && grep -q 'CLASS_RUN_CAP: Final\[int\] = 30' apps/api/src/services/llm_budget.py`
- [ ] The existing workflow-driven `start_interview_run` still works for the main page — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests -q`
- [ ] The R analysis suite still passes — check: `/usr/local/bin/Rscript analysis/tests/test_all.R`

## Out of scope

- Changing the global cache mode default.
- Touching the main workflow page or its tabs.
- Re-recording the Qwen interviews whose reasoning leaked into the answer text (separate issue).
- Provider pinning on OpenRouter.

## Added by Sol refute (each needs a check before it can pass)
- [ ] (sol) A classroom student without a Clerk login can start and view a batch through the deployed web proxy with the same classroom identity used for chat. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k classroom_identity && cd apps/web && npm run test:unit`
- [ ] (sol) The student sees batch progress and can read each completed persona transcript without reloading. — check: `cd apps/web && npm run test:unit`
- [ ] (sol) Each persona receives a complete interview using the selected interviewer for adaptive questions and the selected interviewee for answers, with history isolated between personas. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'adaptive or selected_models'`
- [ ] (sol) The page displays measured batch cost beside the estimate captured when that batch started. — check: `cd apps/web && npm run test:unit`
- [ ] (sol) Invalid batch sizes, unavailable personas, unknown models, and expensive models without explicit opt-in are rejected before any paid call. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'validation or unavailable'`
- [ ] (sol) Both interviewer and interviewee calls count toward one batch budget across all personas, including calls completed before a later failure. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'quota_stop or failure_status'`
- [ ] (sol) A budget stop visibly identifies the exhausted cap and preserves completed transcripts and incurred cost. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k quota_stop && cd apps/web && npm run test:unit`
- [ ] (sol) Provider failures and network interruptions leave completed work recoverable and allow retry without silently repeating paid work. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'failure_status or network_failure' && cd apps/web && npm run test:unit`
- [ ] (sol) Duplicate submissions and concurrent batch, chat, comparison, or regenerate requests neither double-charge the same operation nor bypass shared budget enforcement. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'concurrent or duplicate or failure_status or exact_context'`
- [ ] (sol) Students can regenerate an answer directly in both the chat transcript and an individual model-comparison card. — check: `cd apps/web && npm run test:unit`
- [ ] (sol) Regeneration preserves the original persona, model, question, and preceding history and updates only the selected answer. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'exact_context or comparison_only' && cd apps/web && npm run test:unit`
- [ ] (sol) Regenerating an earlier answer either invalidates dependent follow-ups or is disallowed once follow-ups exist. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k followup_guards && cd apps/web && npm run test:unit`
- [ ] (sol) A failed regeneration preserves the previous displayed and cached answer and leaves the control usable for retry. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k failure_preserves && cd apps/web && npm run test:unit`
- [ ] (sol) Regenerated answers appear consistently in subsequent conversation history, transcript downloads, and any displayed post-interview score. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'exact_context or comparison_only' && cd apps/web && npm run test:unit`
- [ ] (sol) Switching personas or starting another activity cannot attach an in-flight result to the wrong transcript or model. — check: `cd apps/web && npm run test:unit`
- [ ] (sol) New batch and regenerate routes enforce study ownership and prevent supplied session identifiers from charging or modifying another student’s session. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'ownership or classroom_identity'`
- [ ] (sol) Standalone batches preserve saved workflow sections and remain separate from the main workflow’s latest interview run and insights. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'saved_workflow or without_preview'`
- [ ] (sol) An operator can identify a failed batch’s run, persona, model, completed progress, and recorded spend from persisted status or logs. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k failure_status`
