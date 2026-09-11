# DONE — /interview: run the AI-to-AI batch, and regenerate a cached answer

Goal: on `apps/web/src/app/interview/page.tsx` a student can actually run the AI-to-AI batch the
slider sizes, and can force a fresh answer when the cache replays an identical one.

**Decision already made, do not revisit.** The batch uses the page's own fixed 30 personas and the
research brief already hardcoded for this page. It does NOT read study section state (Audience,
Product, Market, Survey) and does NOT require a persona-preview run. Anderson, 2026-09-10: "lets
ignore the workflow state." There are zero `persona_preview_runs` rows in the database, students
never see those tabs, and `scripts/prerecord_interviews.py` already runs headlessly off the same
fixed personas and brief.

Checks execute from this plan directory. Each command first enters the repository root
with `cd ../..`, so it verifies the current worktree rather than a machine-specific checkout.
Default API check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q`.

## Outcome 1 — the batch actually runs

- [x] The batch entry point runs N personas from the page's fixed set with a stubbed provider and needs no persona-preview run and no section rows — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k batch`
- [x] `personaCount` reaches that entry point instead of only the cost estimator: the page issues a request carrying the slider value and the two selected models — check: `cd ../.. && grep -n "personaCount" apps/web/src/app/interview/page.tsx | grep -v preflight`
- [x] A budget stop during a batch surfaces as a quota error carrying the cap that tripped, not a generic failure — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k budget`
- [x] Re-running the same personas and questions replays from cache and records zero new cost — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k batch`
- [x] The run's measured cost is returned to the caller so the page can show it against the pre-flight estimate — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k batch`

## Outcome 2 — regenerate a cached answer

- [x] A regenerate request calls the provider for a question whose answer is already cached — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`
- [x] A normal request for that same question still replays from cache afterwards, so the override is per-request and the global cache mode is untouched — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`
- [x] The regenerated answer is itself cached, so the next identical normal request is free — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`
- [x] Regenerating is subject to the same budget caps as any paid call — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q -k regenerate`

## Nothing already working broke

- [x] Full API suite passes — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q`
- [x] The pre-record script is untouched — check: `cd ../.. && git diff --quiet HEAD -- scripts/prerecord_interviews.py apps/api/tests/test_prerecord_interviews.py`
- [x] The cost report and its tests are untouched — check: `cd ../.. && git diff --quiet HEAD -- docs/cost-report.md apps/api/tests/test_cost_report.py`
- [x] Budget constants are unchanged — check: `cd ../.. && grep -q 'RUN_BUDGET_USD: Final\[Decimal\] = Decimal("0.75")' apps/api/src/services/llm_budget.py && grep -q 'CLASS_RUN_CAP: Final\[int\] = 30' apps/api/src/services/llm_budget.py`
- [x] The existing workflow-driven `start_interview_run` still works for the main page — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests -q`
- [x] The R analysis suite still passes — check: `cd ../.. && /usr/local/bin/Rscript analysis/tests/test_all.R`

## Out of scope

- Changing the global cache mode default.
- Touching the main workflow page or its tabs.
- Re-recording the Qwen interviews whose reasoning leaked into the answer text (separate issue).
- Provider pinning on OpenRouter.

## Added by Sol refute (each needs a check before it can pass)
- [x] (sol) A classroom student without a Clerk login can start and view a batch through the deployed web proxy with the same classroom identity used for chat. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k classroom_identity && cd apps/web && npm run test:unit`
- [x] (sol) The student sees batch progress and can read each completed persona transcript without reloading. — check: `cd ../.. && cd apps/web && npm run test:unit`
- [x] (sol) Each persona receives a complete interview using the selected interviewer for adaptive questions and the selected interviewee for answers, with history isolated between personas. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'adaptive or selected_models'`
- [x] (sol) The page displays measured batch cost beside the estimate captured when that batch started. — check: `cd ../.. && cd apps/web && npm run test:unit`
- [x] (sol) Invalid batch sizes, unavailable personas, unknown models, and expensive models without explicit opt-in are rejected before any paid call. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'validation or unavailable'`
- [x] (sol) Both interviewer and interviewee calls count toward one batch budget across all personas, including calls completed before a later failure. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'quota_stop or failure_status'`
- [x] (sol) A budget stop visibly identifies the exhausted cap and preserves completed transcripts and incurred cost. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k quota_stop && cd apps/web && npm run test:unit`
- [x] (sol) Provider failures and network interruptions leave completed work recoverable and allow retry without silently repeating paid work. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'failure_status or network_failure' && cd apps/web && npm run test:unit`
- [x] (sol) Duplicate submissions and concurrent batch, chat, comparison, or regenerate requests neither double-charge the same operation nor bypass shared budget enforcement. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'concurrent or duplicate or failure_status or exact_context'`
- [x] (sol) Students can regenerate an answer directly in both the chat transcript and an individual model-comparison card. — check: `cd ../.. && cd apps/web && npm run test:unit`
- [x] (sol) Regeneration preserves the original persona, model, question, and preceding history and updates only the selected answer. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'exact_context or comparison_only' && cd apps/web && npm run test:unit`
- [x] (sol) Regenerating an earlier answer either invalidates dependent follow-ups or is disallowed once follow-ups exist. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k followup_guards && cd apps/web && npm run test:unit`
- [x] (sol) A failed regeneration preserves the previous displayed and cached answer and leaves the control usable for retry. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k failure_preserves && cd apps/web && npm run test:unit`
- [x] (sol) Regenerated answers appear consistently in subsequent conversation history, transcript downloads, and any displayed post-interview score. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'exact_context or comparison_only' && cd apps/web && npm run test:unit`
- [x] (sol) Switching personas or starting another activity cannot attach an in-flight result to the wrong transcript or model. — check: `cd ../.. && cd apps/web && npm run test:unit`
- [x] (sol) New batch and regenerate routes enforce study ownership and prevent supplied session identifiers from charging or modifying another student’s session. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'ownership or classroom_identity'`
- [x] (sol) Standalone batches preserve saved workflow sections and remain separate from the main workflow’s latest interview run and insights. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'saved_workflow or without_preview'`
- [x] (sol) An operator can identify a failed batch’s run, persona, model, completed progress, and recorded spend from persisted status or logs. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k failure_status`

## Added after refuter round 1 (blocker F1)
- [x] (refuter F1) Once a batch step has failed, a duplicate request that was already queued carrying the same revision cannot issue another paid provider call; only an explicit retry initiated by the student can. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'failed_advance_requires_explicit_retry'`

## Added by Sol refute (each needs a check before it can pass)
- [x] (sol) After a batch creation request is rejected, the student can correct the settings and successfully start a batch without clearing browser storage. — check: `cd ../.. && cd apps/web && npm run test:unit`
- [x] (sol) A returning student can reopen completed or paused batches after closing the tab or starting another batch, with transcripts and measured costs preserved. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k batch_history && cd apps/web && npm run test:unit`
- [x] (sol) Standalone batches respect the existing per-user daily run limit without counting each advance or duplicate submission as another run. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k daily_run_limit`
- [ ] (refuter R1) The same guarantee holds on the regenerate path: once a regeneration has failed with an unknown provider outcome, a duplicate request already queued at the same version cannot issue another paid call; only an explicit retry can. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_batch.py -q -k 'failed_regeneration_requires_explicit_retry'`
