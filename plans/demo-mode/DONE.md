Goal: one app-wide "Demo (no AI)" switch that puts /focus-group, /interview and /interview/you into demo together, each opening a finished, pre-recorded example session with zero model calls, for Dr. Lin's class on Wed 2026-10-07. Live mode unchanged. Spec: BRIEF.md.

Checks run from this directory through `./check.sh`.

## Focus group demo

- [x] Opening the focus-group demo creates (or re-opens) one room in the student's own study, flagged demo, containing the full fixture: at least 6 seated personas with cards, the concept introduced, the price revealed after the unaided question, at least one targeted question and one probe, and all five stages reached. — check: `./check.sh api 'focus_group_demo_opens'`
- [x] Opening the demo twice returns the same room, not a second copy. — check: `./check.sh api 'demo_open_is_idempotent'`
- [x] In a demo room the manual memo (quote a turn, save, draft restore) and export (Markdown and CSV) work exactly as in a live room, and every export carries "Demo session - pre-recorded, no AI". — check: `./check.sh api 'focus_group_demo_memo_and_export'`
- [x] Ask, introduce, reveal, retry, extend and AI memo on a demo room are refused with a plain "Demo (no AI): read-only" message before any model, budget or charge code runs. — check: `./check.sh api 'focus_group_demo_refuses_ai'`

## Interview demos

- [x] Opening the interview-batch demo creates (or re-opens) one finished batch, flagged demo, with at least 6 personas answering the default guide; it can be read and exported, and the export carries the demo label. — check: `./check.sh api 'interview_batch_demo'`
- [x] Advance, regenerate and theme generation on a demo batch are refused before any model, budget or charge code runs. — check: `./check.sh api 'interview_batch_demo_refuses_ai'`
- [x] The "AI interviews you" demo returns a sample transcript of 8 questions with follow-ups and answers, read-only, exportable with the demo label, and no next-question call is made. — check: `./check.sh api 'interview_you_demo'`

## Zero AI, no wider access

- [x] Opening, reading, memo-saving and exporting every demo makes zero provider calls and records zero spend: the test replaces the model client with one that fails the test if called. — check: `./check.sh api 'demo_makes_no_model_calls'`
- [x] Demo endpoints work on the classroom no-login path with no OpenRouter key configured, and nothing wider was opened on the allowlist (other methods, suffixes and encoded paths still refused). — check: `./check.sh api 'demo_no_key_no_login'`
- [x] Demo sessions live only in the student's own study: another classroom device cannot list or open them. — check: `./check.sh api 'demo_isolated_per_study'`
- [x] The committed fixtures were produced by `apps/api/scripts/make_demo_fixtures.py` from a real model run (none marked provisional) and contain no real survey respondent data. — check: `./check.sh fixtures`

## Pages

- [x] One "Demo (no AI)" switch in the shared app chrome appears on every page; turning it on puts /interview, /interview/you and /focus-group into demo together, it persists across navigation and reload, and `apps/web/src/lib/demo-mode.ts` exports `useDemoMode()` and the storage key for the survey section to read. — check: `./check.sh web 'demo switch'`
- [x] With the switch on, each of the three pages shows its demo session with AI controls hidden or disabled and the "Demo (no AI): read-only" note, the "Demo session - pre-recorded, no AI" label is visible, and the memo form and export stay usable; with it off, the pages are exactly as before. — check: `./check.sh web 'demo mode'`

## Nothing else broke

- [x] The full API suite passes. — check: `./check.sh api-all`
- [x] The full web suite passes, the web app typechecks and the production build succeeds. — check: `./check.sh web-all && ./check.sh typecheck && ./check.sh build`

## Added by Sol refute [codex:gpt-6-astra] (each needs a check before it can pass)
- [x] (sol) A first-time student with an empty study can open each demo without configuring models, personas, a product, or a guide. — check: `./check.sh api 'demo_no_key_no_login'`
- [x] (sol) Demo access remains available when live-run budgets or quotas are exhausted. — check: `./check.sh api 'demo_makes_no_model_calls'`
- [x] (sol) Concurrent demo opens and retries after a lost response produce one complete copy without resetting the student's saved memo. — check: `./check.sh api 'demo_concurrent_first_open or focus_group_demo_memo_and_export'`
- [x] (sol) A failed demo load shows a recoverable error, leaves no partial session, and never falls back to a live run. — check: `./check.sh api 'missing_fixture_no_partial_copy or demo_invalid_fixture' && ./check.sh web 'demo mode opens'`
- [x] (sol) Returning through refresh or session history preserves the demo flag, labels, and read-only restrictions. — check: `./check.sh api 'demo_history_retains' && ./check.sh web 'demo mode opens'`
- [x] (sol) Switching between demo and live sessions preserves existing transcripts and memo drafts, and late responses cannot overwrite the newly selected session. — check: `./check.sh web 'demo mode opens|demo switch during live advance|demo mode isolates'`
- [x] (sol) Saved fixture themes can be viewed with valid transcript citations, while fixtures without themes clearly report their absence without offering generation. — check: `./check.sh api 'demo_saved_themes or interview_batch_demo'`
- [x] (sol) Direct next-question requests and alternate chat or comparison endpoints cannot use a demo session identifier to trigger model or budget work. — check: `./check.sh api 'demo_alternate or interview_you_demo'`
- [x] (sol) Another student cannot export, modify memos, delete, or otherwise mutate a demo by supplying its identifiers. — check: `./check.sh api 'demo_foreign_device or demo_isolated_per_study'`
- [x] (sol) After classroom-session expiry or shared-device reset, the next student cannot recover the previous student's demo memos through browser storage. — check: `./check.sh web 'demo mode isolates' && ./check.sh api 'demo_foreign_device'`
- [x] (sol) Opening demos leaves existing study configuration, survey results, live transcripts, and research analysis unchanged. — check: `./check.sh api 'demo_preserves_existing_data'`
- [x] (sol) Every demo screen and export retains the existing “Synthetic rehearsal” label alongside the demo label. — check: `./check.sh web 'demo mode batch and human exports' && ./check.sh api 'focus_group_demo_memo_and_export'`
- [x] (sol) Fixture generation uses the real service code and enforces the approved $2 total spending limit. — check: `./check.sh api 'demo_generator'`
- [x] (sol) Missing or invalid deployed fixtures produce an actionable operator diagnostic identifying the affected demo without exposing student content. — check: `./check.sh api 'missing_fixture_no_partial_copy or demo_invalid_fixture'`

## Added by Sol refute [codex:gpt-6-astra] (each needs a check before it can pass)
- [x] (sol) Turning demo mode on during a live batch stops subsequent automatic advance requests, clearly identifies any already-running paid request, and requires explicit action to resume paid work after demo mode is turned off. — check: `./check.sh web 'demo switch during live advance'`
- [x] (sol) Changing the switch in one browser tab updates other open app tabs so they cannot silently remain in live mode. — check: `./check.sh web 'demo switch cross-tab subscriber'`
- [x] (sol) Opening demos consumes no daily interview-run quota and leaves the student's remaining live-run allowance unchanged. — check: `./check.sh api 'demo_preserves_existing_data_and_quota'`
- [x] (sol) Deleting a demo focus-group room cannot strand the demo page, and reopening provides a complete usable example without resurrecting deleted memos. — check: `./check.sh api 'focus_group_demo_memo_and_export'`
- [x] (sol) Demo screens and exports show zero cost for the student's playback and clearly distinguish any historical fixture-generation cost. — check: `./check.sh api 'focus_group_demo_opens' && ./check.sh web 'demo mode batch and human exports'`
- [x] (sol) A student's previously selected product photo or custom concept cannot appear attached to the prerecorded Tahoe Mini discussion. — check: `./check.sh api 'demo_preserves_existing_data' && ./check.sh web 'demo mode isolates'`
- [x] (sol) Keyboard and screen-reader users can operate the shared switch and determine whether demo mode is on in both desktop and compact navigation. — check: `./check.sh web 'demo switch native accessible'`
