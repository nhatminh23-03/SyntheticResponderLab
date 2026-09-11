Goal: a student in Dr. Lin's class can run the interview section without being overwhelmed, cannot spend real money by accident, and ends up with extracted themes they can compare against their own hand-coding.

## Outcomes

- [x] After a student completes an interview run in the standalone interview section, they can see 3–6 extracted themes from their own transcripts, each with a representative quote, without leaving the page. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q -k 'standalone_themes'`
- [x] The theme extraction reuses the existing insights service rather than a second implementation, and a student's themes come from their own session's transcripts, never another student's or the main workflow's latest run. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q -k 'standalone_themes_scoped'`
- [x] Re-opening the themes for a run a student already generated does not make another paid call. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q -k 'standalone_themes and cached'`
- [x] A student cannot start a run that uses an expensive model without first checking the expensive-model box; moving the persona slider alone can never reach an expensive configuration. — check: `cd ../../apps/web && npm run test:unit`
- [x] Before a batch run starts, the student sees what it will cost and confirms it; dismissing the confirmation starts nothing and spends nothing. — check: `cd ../../apps/web && npm run test:unit`
- [x] A student landing on the interview section sees one step at a time rather than every control at once, and can move between steps and back again without losing a run in progress or a completed transcript. — check: `cd ../../apps/web && npm run test:unit`
- [x] Every screen the student can reach has a way back to the previous one. — check: `cd ../../apps/web && npm run test:unit`
- [x] Nothing already working broke — the main gated workflow, the model comparison, the follow-up chat, the pre-recorded interviews page and the batch/regenerate controls all still work. — check: `cd ../../apps/web && npm run test:unit && cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/ -q`

## Don't touch

- `scripts/prerecord_interviews.py`
- the main gated workflow's interview run and its insights
- the budget constants and `enforce_run_preflight` / `enforce_measured_cost`
- `docs/` cost report and `apps/api/tests/test_cost_report.py`
- no teacher/student role or permission system — Lin asked for a checkbox

## Added by Sol refute (each needs a check before it can pass)
- [x] (sol) Students using classroom no-login mode can generate and retrieve themes through the application proxy without encountering a login requirement. — check: `cd ../../apps/web && npm run test:unit`
- [x] (sol) Theme extraction respects cache-only mode, the zero-dollar kill switch, and existing run and class budgets, with incurred extraction costs included in measured usage. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) Students explicitly authorize any additional theme-extraction charge before it occurs, including when opening results or returning to a step. — check: `cd ../../apps/web && npm run test:unit`
- [x] (sol) Double-clicks, concurrent tabs, and repeated requests for the same transcript revision produce one extraction charge and one saved result. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) If extraction times out with an unknown billing outcome, students are warned before explicitly retrying rather than triggering automatic additional paid calls. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) Empty, unfinished, failed, and budget-stopped runs show an accurate explanation of theme availability without charging for an empty corpus or presenting partial transcripts as a completed run. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) Extraction failures and malformed model responses leave transcripts accessible and show a recoverable error rather than an empty success or indefinite loading state. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) Every representative quote is verbatim from an identified interviewee transcript that the student can locate for comparison with their hand-coding. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) After regeneration or additional follow-up answers change a transcript, previously extracted themes are clearly marked as belonging to the earlier version. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
- [x] (sol) Switching saved runs while extraction is pending cannot display the earlier run’s themes under the newly selected run. — check: `cd ../../apps/web && npm run test:unit`
- [x] (sol) The batch confirmation identifies the exact persona count, both models, and estimated cost being authorized, and changed settings or recovered requests cannot reuse confirmation for a different configuration. — check: `cd ../../apps/web && npm run test:unit`
- [x] (sol) Refreshing or returning to a saved batch restores its transcripts and generated themes without restarting paid work. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q && cd apps/web && npm run test:unit`
- [x] (sol) Keyboard and screen-reader users can navigate the steps and operate or dismiss the cost confirmation with predictable focus. — check: `cd ../../apps/web && npm run test:unit`
- [x] (sol) An operator investigating extraction failures can identify the affected study, run, transcript revision, and known or unknown charge outcome without exposing transcript contents or credentials in logs. — check: `cd ../.. && ./apps/api/.venv/bin/python -m pytest apps/api/tests/test_standalone_themes.py -q`
