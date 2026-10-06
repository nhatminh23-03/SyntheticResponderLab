Goal: a "Demo (no AI)" option on /focus-group, /interview and /interview/you that opens a finished, pre-recorded example session with zero model calls, for Dr. Lin's class on Wed 2026-10-07. Live mode unchanged. Spec: BRIEF.md.

Checks run from this directory through `./check.sh`.

## Focus group demo

- [ ] Opening the focus-group demo creates (or re-opens) one room in the student's own study, flagged demo, containing the full fixture: at least 6 seated personas with cards, the concept introduced, the price revealed after the unaided question, at least one targeted question and one probe, and all five stages reached. — check: `./check.sh api 'focus_group_demo_opens'`
- [ ] Opening the demo twice returns the same room, not a second copy. — check: `./check.sh api 'demo_open_is_idempotent'`
- [ ] In a demo room the manual memo (quote a turn, save, draft restore) and export (Markdown and CSV) work exactly as in a live room, and every export carries "Demo session - pre-recorded, no AI". — check: `./check.sh api 'focus_group_demo_memo_and_export'`
- [ ] Ask, introduce, reveal, retry, extend and AI memo on a demo room are refused with a plain "Demo (no AI): read-only" message before any model, budget or charge code runs. — check: `./check.sh api 'focus_group_demo_refuses_ai'`

## Interview demos

- [ ] Opening the interview-batch demo creates (or re-opens) one finished batch, flagged demo, with at least 6 personas answering the default guide; it can be read and exported, and the export carries the demo label. — check: `./check.sh api 'interview_batch_demo'`
- [ ] Advance, regenerate and theme generation on a demo batch are refused before any model, budget or charge code runs. — check: `./check.sh api 'interview_batch_demo_refuses_ai'`
- [ ] The "AI interviews you" demo returns a sample transcript of 8 questions with follow-ups and answers, read-only, exportable with the demo label, and no next-question call is made. — check: `./check.sh api 'interview_you_demo'`

## Zero AI, no wider access

- [ ] Opening, reading, memo-saving and exporting every demo makes zero provider calls and records zero spend: the test replaces the model client with one that fails the test if called. — check: `./check.sh api 'demo_makes_no_model_calls'`
- [ ] Demo endpoints work on the classroom no-login path with no OpenRouter key configured, and nothing wider was opened on the allowlist (other methods, suffixes and encoded paths still refused). — check: `./check.sh api 'demo_no_key_no_login'`
- [ ] Demo sessions live only in the student's own study: another classroom device cannot list or open them. — check: `./check.sh api 'demo_isolated_per_study'`
- [ ] The committed fixtures were produced by `apps/api/scripts/make_demo_fixtures.py` from a real model run (none marked provisional) and contain no real survey respondent data. — check: `./check.sh fixtures`

## Pages

- [ ] Each of the three pages shows a "Demo (no AI)" button; in demo the AI controls are hidden or disabled with the "Demo (no AI): read-only" note, the "Demo session - pre-recorded, no AI" label is visible, and the memo form and export stay usable. — check: `./check.sh web 'demo mode'`

## Nothing else broke

- [ ] The full API suite passes. — check: `./check.sh api-all`
- [ ] The full web suite passes, the web app typechecks and the production build succeeds. — check: `./check.sh web-all && ./check.sh typecheck && ./check.sh build`
