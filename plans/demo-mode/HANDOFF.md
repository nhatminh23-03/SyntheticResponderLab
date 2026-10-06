# Demo mode handoff — round 1

Base commits: `7ca4fbf` (previous build round), `ff2c81a` (shared switch plan),
`b6e0b4f` (earlier build round), `98a2e02` (initial plan). The working tree was clean
at entry. This round's source, tests, fixtures and decisions are uncommitted and
must be preserved. No board writes, commits, deployments, survey changes or
research/scoring changes were made. No repository vault is present.

Read `BRIEF.md`, `DONE.md` and `DECISIONS.md`. The implementation entry points are
`apps/api/src/services/demo_mode.py`, `apps/api/scripts/make_demo_fixtures.py`,
`apps/web/src/lib/demo-mode.ts` and `apps/web/src/components/demo/demo-mode.tsx`.
The three existing classroom pages use separate live/demo component instances;
live batch advance stops on the switch and requires explicit Resume after return.
The exact new no-login allowlist entries are POST interview/demo/{focus-group,batch,you}.

The API settings were checked without displaying credentials: no OpenRouter key is
available. All three checked-in JSON files are explicitly `provisional: true` and
are visibly labeled handwritten examples in pages/exports. Do not remove that flag
manually. The next release patch is to run, from `apps/api`, with a configured key:

```sh
python scripts/make_demo_fixtures.py
../../plans/demo-mode/check.sh fixtures
```

The generator uses an isolated temporary database, existing services and seed
personas. It never reads student studies or real survey responses. It reserves
cost across every call, disables retries and caps completion tokens. Use a
provider key capped at $2 as an external billing ceiling. Existing playback copies
are not overwritten when fixtures change, to preserve saved student memos.

Focused verification before regression: `check.sh api 'demo'` (16 passed),
`check.sh web 'demo'` (5 passed), `check.sh typecheck`, `git diff --check`.
The fixture-realness gate is expected to remain red until the real recording.
The wrapper owns mutation checks and deployed-site verification; neither was run
by the builder. Full regression results are recorded below when available.

Local dependencies: `apps/web/node_modules` is a symlink to the existing checkout's
installed dependencies, ignored by Git (the ignore rule now handles symlinks as
well as directories). Do not commit machine-local dependency links.

Final verification:

- Full API suite: **595 passed, 13 skipped** (existing opt-in skips).
- Full web suite ran once: 155 passed, 40 failed because the old test harness did
  not mock the new wrapper/hook imports and four source assertions pinned the old
  markup/restore count. Updated the harness to traverse the render callback and
  supplied live-mode mocks; updated assertions to include read-only guards and
  the third memo-restore path. All **82 tests in the affected four suites passed**
  on their focused rerun. The entire suite was not repeated, per the run limit.
- Added real page-handler tests for demo loading/export/no generation and switching
  during a live advance. Final `check.sh web 'demo'`: **7 passed**.
- Final TypeScript check and `git diff --check`: passed.
- Production build: passed (before the final optional-props default/test-harness
  corrections; final source subsequently typechecked). Existing Browserslist
  staleness and webpack cache-size warnings only.
- `check.sh fixtures`: fails as expected because `batch.json` is provisional;
  all three fixtures are provisional. This is the outstanding release blocker.

Exact generation command using the available environment, from repository root
(after configuring `OPENROUTER_API_KEY` in API settings):

```sh
/Users/andersonedmond/dev/SyntheticResponderLab/apps/api/.venv/bin/python apps/api/scripts/make_demo_fixtures.py
plans/demo-mode/check.sh fixtures
```

The builder did not run mutation scripts or deployed-site verification. The
wrapper owns those. Do not mark ALL DONE while fixture realness is red.


## Round 2

Entry commit: `06dc048` (demo-mode: build round 1); prior commits `7ca4fbf`,
`ff2c81a`, `b6e0b4f`. The wrapper/user had modified DONE.md at entry; its added
outcomes are preserved and now have executable check commands. Preserve all
current dirty files: API service guard ordering, API/web demo tests, DONE.md,
DECISIONS.md and this handoff. No survey, scoring, prompts or fixtures were changed.

Added behavioral tests for concurrent reopening with a saved memo, all-table
preservation (including quota), saved themes and rejection of fabricated citations,
history flags, generator service calls and cost reservations, alternate HTTP AI
routes, rendered native switch state, and cross-tab notification cleanup. Static
checks additionally cover photo/control isolation and browser memo storage guards;
these do not replace harness verification in a real deployed browser.

The alternate chat and interviewer-question routes now reject demo IDs before
checking live-only prerequisites. This corrects misleading errors in empty studies;
live inputs continue through the existing logic. Design decision 1 records this.

Focused checks: 22 API demo tests and 10 web demo tests; typecheck and diff check.
Full regression results follow. No mutation scripts or deployment were run.
The real-model fixture gate remains pending; do not mark ALL DONE or remove the
provisional flags. Next patch remains the real fixture-generation command above.

Round 2 final regression (run once): **601 API passed, 13 skipped; 200 web
passed; production build passed; TypeScript and `git diff --check` passed**.
Logs: `/tmp/demo-round2-api.log`, `/tmp/demo-round2-web.log`,
`/tmp/demo-round2-build.log`. Skips are existing opt-in tests. No mutation suite
was run. Added outcome checkboxes reflect their executable checks; deployed
browser behavior remains for the harness. The final action attempts the real
fixture generator, which fails closed if API settings still lack a key.
