Goal: a student in Dr. Lin's class can run the interview section without being overwhelmed, cannot spend real money by accident, and ends up with extracted themes they can compare against their own hand-coding.

## Outcomes

- [ ] After a student completes an interview run in the standalone interview section, they can see 3–6 extracted themes from their own transcripts, each with a representative quote, without leaving the page. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q -k 'standalone_themes'`
- [ ] The theme extraction reuses the existing insights service rather than a second implementation, and a student's themes come from their own session's transcripts, never another student's or the main workflow's latest run. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q -k 'standalone_themes_scoped'`
- [ ] Re-opening the themes for a run a student already generated does not make another paid call. — check: `./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q -k 'standalone_themes_cached'`
- [ ] A student cannot start a run that uses an expensive model without first checking the expensive-model box; moving the persona slider alone can never reach an expensive configuration. — check: `cd apps/web && npm run test:unit`
- [ ] Before a batch run starts, the student sees what it will cost and confirms it; dismissing the confirmation starts nothing and spends nothing. — check: `cd apps/web && npm run test:unit`
- [ ] A student landing on the interview section sees one step at a time rather than every control at once, and can move between steps and back again without losing a run in progress or a completed transcript. — check: `cd apps/web && npm run test:unit`
- [ ] Every screen the student can reach has a way back to the previous one. — check: `cd apps/web && npm run test:unit`
- [ ] Nothing already working broke — the main gated workflow, the model comparison, the follow-up chat, the pre-recorded interviews page and the batch/regenerate controls all still work. — check: `cd apps/web && npm run test:unit && cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q`

## Don't touch

- `scripts/prerecord_interviews.py`
- the main gated workflow's interview run and its insights
- the budget constants and `enforce_run_preflight` / `enforce_measured_cost`
- `docs/` cost report and `apps/api/tests/test_cost_report.py`
- no teacher/student role or permission system — Lin asked for a checkbox
