# 06 — Fix Log

> **Rule.** Every fix must reference a verified finding ID, identify the root cause, list files changed, list tests added or changed, and include post-fix verification evidence.

No fix may be recorded here until the change has been made **and re-verified**. A finding is not "fixed" because a change was written — only because the original reproduction no longer reproduces and a regression test covers it.

**Working branch:** `fix/f-11-quota-race`, cut from `yaza_Aug_work` @ `7645dfa`.

---

## F-11 — Daily quota first-request race

### Original behavior
The first quota-metered request of a UTC day for a given user could return **HTTP 500** when two requests
arrived concurrently. Observed first in the browser: clicking **Start Setup** produced
`POST /api/backend/api/v1/studies → 500`, a blank page, and a console error, with no recovery guidance.

Because the counter bucket is keyed on the **UTC date**, the window opens for every user at the start of each
day, and applies to **all** quota-metered actions: study creation, survey/image upload, simulation runs,
stability checks and interview runs.

### Reproduction
```
# clear the counter row to simulate the first request of a UTC day, then fire two concurrent creates
sqlite3 qa.db "DELETE FROM user_usage_counters;"
curl -X POST .../api/v1/studies & curl -X POST .../api/v1/studies & wait

attempt 1: A=500 B=200
attempt 2: B=200 A=500
attempt 3: B=200 A=500
attempt 4: A=200 B=500        -> 4/4 reproduce
```
```
sqlite3.IntegrityError: UNIQUE constraint failed:
  user_usage_counters.owner_user_id, user_usage_counters.metric_key, user_usage_counters.bucket_date_utc
```
With the counter row already present, concurrent requests all returned 200 — confirming the window is the
**INSERT of the first counter row** for a `(owner_user_id, metric_key, bucket_date_utc)` triple.

### Root cause
`src/services/usage_limits.py::consume_daily_quota` performed a **check-then-act**: a `SELECT` for the
counter row, then a conditional `INSERT` of a new row or an in-Python `row.count += 1`.

```python
row = session.scalar(select(UserUsageCounter).where(...))
current_count = row.count if row else 0
...
if row is None:
    row = UserUsageCounter(..., count=1)
else:
    row.count += 1
session.add(row)
```

The table's `UniqueConstraint uq_user_usage_counters_owner_metric_bucket` correctly prevents duplicates at
the database level, but nothing in the code handled the resulting conflict. Two requests that both observe a
missing row both attempt the `INSERT`; the second violates the constraint, and the unhandled `IntegrityError`
surfaces at commit as a 500.

A secondary latent defect in the same statement: `row.count += 1` is a read-modify-write, so two concurrent
increments could lose one another's update and under-count the quota.

**Prior art check:** a repo-wide grep of `src/` for `IntegrityError`, `on_conflict`, `begin_nested`,
`savepoint` and `with_for_update` returned **no existing atomic-insert pattern** to follow, so one had to be
introduced.

### Regression test added
`apps/api/tests/test_usage_limits.py::test_concurrent_first_request_of_day_does_not_error`

A sequential call cannot reproduce this — the second call simply sees the row created by the first. The test
therefore releases **two threads from a `threading.Barrier`** so their read/insert windows overlap against a
fresh per-test database (which naturally satisfies the first-request-of-day condition), and asserts both
requests return 200.

Confirmed to **fail on the unchanged implementation**:
```
FAILED tests/test_usage_limits.py::test_concurrent_first_request_of_day_does_not_error
sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint failed: ...
```

### Files changed
- `apps/api/src/services/usage_limits.py` — added `_increment_usage_counter`; `consume_daily_quota` now calls
  it instead of building/mutating an ORM row. Added `import uuid`.
- `apps/api/tests/test_usage_limits.py` — added the concurrency regression test.

No other files were touched. (`NeoSmart-Hackathon-App` and `apps/web/package-lock.json` also appear in
`git diff` in the QA worktree; those are **QA-harness artifacts** — a symlink standing in for the broken
gitlink of F-01, and `npm install` — not part of this fix.)

### Fix
Replaced the read-then-insert with a single atomic `INSERT … ON CONFLICT DO UPDATE`, dispatched to the
PostgreSQL or SQLite dialect (production is Postgres, local is SQLite; both support it, and SQLite 3.53
supports `RETURNING`):

```python
statement = (
    _dialect_insert(table)
    .values(id=uuid.uuid4(), owner_user_id=..., metric_key=..., bucket_date_utc=bucket,
            count=1, created_at=now, updated_at=now)
    .on_conflict_do_update(
        index_elements=[table.c.owner_user_id, table.c.metric_key, table.c.bucket_date_utc],
        set_={"count": table.c.count + 1, "updated_at": now},
    )
    .returning(table.c.count)
)
return int(session.scalar(statement))
```

The database now resolves the collision, and the increment is atomic rather than a read-modify-write — so
this also closes the latent lost-update path. The existing `SELECT` is retained solely for the quota-limit
check, and the limit-exceeded behaviour is unchanged. No unrelated refactoring.

### Verification
| Check | Result |
|---|---|
| New regression test | **1 passed** (failed before the change) |
| Surrounding quota tests (`tests/test_usage_limits.py`) | **11 passed** |
| Full backend suite | **65 passed, 1 failed** |
| HTTP reproduction, 6 fresh-counter races | **6/6 → `A=200 B=200`** (was 4/4 producing a 500) |
| Counter integrity after the races | `count = 2` — **both increments recorded, no lost update** |
| Post-fix backend log | **0** `IntegrityError`, **0** `500` |
| Browser Study Setup path | two concurrent `POST /studies` → **200, 200**; double-clicked **Start Setup**; section renders `01. STUDY SETUP`; all current network requests 200 |

The single remaining suite failure is `test_studies_endpoints.py::test_product_provider_gaps_fail_clearly`
— that is **F-02**, the pre-existing regression introduced by `7645dfa` and explicitly out of scope here.
It failed identically before this change (`64 passed, 1 failed` → now `65 passed, 1 failed`, the extra pass
being the new test).

A stale `500` entry remained in the browser console buffer from the pre-fix session; it is not a current
request. Verified against the live network log (all 200) and the post-fix backend log (0 occurrences).

### Final pre-commit verification pass (fresh, 2026-08-17)

Re-run from the working tree immediately before committing.

**Working-tree audit.** `git diff --stat` initially showed two changes unrelated to F-11:
- `apps/web/package-lock.json` — mutated by `npm install` during QA setup → **restored to HEAD**.
- `NeoSmart-Hackathon-App` — the QA symlink standing in for the broken gitlink of F-01. It also made
  `git status` fail outright (*"expected submodule path … not to be a symbolic link"*) → **removed before
  committing**, restoring the empty gitlink directory.

Neither was committed. My QA reproduction scripts (`qa_*.py`) were untracked; they have been preserved under
`QA August 17/artifacts/repro-scripts/` and removed from the worktree. Final tracked diff was exactly the two
F-11 files.

**Fresh test runs**
| Suite | Result |
|---|---|
| `tests/test_usage_limits.py::test_concurrent_first_request_of_day_does_not_error` | **1 passed** |
| `tests/test_usage_limits.py` (quota group) | **11 passed** |
| Full backend suite | **65 passed, 1 known pre-existing F-02 failure** |

The F-02 failure is `tests/test_studies_endpoints.py::test_product_provider_gaps_fail_clearly` at line 691,
failing for the identical previously-recorded reason:
```
E  AssertionError: assert 'OPENROUTER_API_KEY is required' in 'URL returned HTTP 404'
```
`git diff --name-only` confirms that test file is **untouched** by this change. No additional tests fail.

**Fresh HTTP concurrency verification against an emptied quota bucket**
```
counter rows before : 0
  request A -> 200
  request B -> 200
counter after       : dev-local-user | study_create | 2026-08-18 | count=2
IntegrityError in backend log : before=0  after=0
500s in backend log           : 0
```
Both requests succeeded, the counter incremented exactly twice (no lost update), and no IntegrityError or
500 was produced.

**Commit:** originally `84b30ed`, rebased to **`599eccf`** on `fix/f-11-quota-race`
(2 files, +88 −12). Working tree clean afterwards. Not pushed, not merged.

### Rebase onto teammate's latest — re-verified 2026-08-20

The fix was originally verified against `7645dfa`. Your teammate then pushed `2691642`
("Improve study workflow and simulation prompts"), so the branch was rebased and re-verified on top of it.

```
before : 84b30ed  on 7645dfa
after  : 599eccf  on 2691642      (clean rebase, no conflicts)
```

**Conflict surface: none.** The fix touches `usage_limits.py` + its test; `2691642` touches 15 other files.
`comm` on the two changed-file lists returns zero overlap, and `git merge-tree` reported a clean merge before
the rebase was run. Post-rebase the branch is still exactly **2 files, +88 −12** against its new base.

**Fresh test runs on `599eccf`:**
| Suite | Result |
|---|---|
| F-11 concurrency regression test | **1 passed** |
| Quota group | **11 passed** |
| Full backend suite | **65 passed, 1 known pre-existing F-02 failure** |

For comparison, `2691642` alone scores **64 passed, 1 failed** — the same F-02 test, same reason. The `+1`
is this branch's regression test. **Combining the two introduced no regressions.**

**Fresh HTTP race on the combined tree**, 5 emptied quota buckets:
```
attempt 1: A=200 B=200 | counter=2
attempt 2: B=200 A=200 | counter=2
attempt 3: A=200 B=200 | counter=2
attempt 4: A=200 B=200 | counter=2
attempt 5: B=200 A=200 | counter=2
IntegrityError in log : 0
500s in log           : 0
```

**Note on the teammate's parallel change.** `2691642` added a `bootstrapStartedRef` guard in
`apps/web/src/providers/study-provider.tsx` to stop React Strict Mode double-firing the study bootstrap — its
comment refers to *"a transient 500"*. That suppresses **one trigger** of F-11 on the client; it does not
change `consume_daily_quota`, so genuine concurrency (two tabs, a real double-click, several students on a
fresh UTC day) still raced before this fix. The two changes are complementary and both are wanted.

**Not pushed, not merged.** Intended target is a PR into `yaza_Aug_work` — **not `main`**, which is 2 commits
behind and carries none of the August work.

### Remaining risks
1. **The quota-limit check is still read-then-act.** Two concurrent requests at exactly the limit boundary
   can both pass the check and increment, allowing the daily cap to be exceeded by the number of racing
   requests. This degrades a limit by one or two rather than throwing a 500, so it was left alone to keep the
   fix minimal. Worth a follow-up that enforces the ceiling in the same statement.
2. **Not exercised against PostgreSQL.** The dialect branch is selected at runtime and the SQLite path is
   covered by tests; the Postgres path is unverified locally. It should be smoke-tested on the Preview
   deployment before release.
3. **`session.expire(row)` on the previously-loaded ORM row** keeps the identity map from serving a stale
   count. No test currently reads the counter through the ORM after consumption, so this is defensive.
4. **The QA harness symlink was removed to commit.** Any further local work in this worktree needs
   `NeoSmart-Hackathon-App` repopulated (symlink to the main checkout, or point `LEGACY_APP_ROOT` at the
   vendored `apps/api/legacy_runtime`) before the backend or its tests will run.
5. **F-01 still applies** — this fix does not change the fact that a fresh clone cannot run the app.


---

## F-07 — Neo interview fixture presented as a live dual-model batch

### Original behavior
`study_mode == "neo_smart"` short-circuits `run_interview_batch` to `ensure_demo_interview_run` **before**
the OpenRouter key check. No interview model and no judge model is ever called. Answers are a hardcoded
`IQ1..IQ8` chain, "Model B" appends a fixed clause to Model A's text, themes are pre-written English, and the
"grounding report" is a lookup table on persona `fit_tier`.

The backend **already recorded** the provenance on the job result — but `_serialize_interview_job` returned
only 10 fields and dropped all three, so **no client could distinguish a fixture from a genuine batch**:

```
backend result_json : demo_fixture=True, fixture_source='generated_fallback', judge_model='demo/stamp-fixture'
client response     : job_id, status, persona_count, model_a, model_b, grounding_report,
                      pairs, error, queued_at, completed_at
```

The UI asserted the opposite — *"Both AI models interview every persona independently. A judge LLM then
scores agreement across four dimensions — STAMP-style"*, a score *"analogous to Krippendorff's α"* — and
displayed **STAMP GROUNDING SCORE 100% · PASSES THRESHOLD** with all four dimensions at 100%.

### Reproduction
Bootstrap a Neo study, `POST /api/v1/studies/{id}/interview/runs`. Response returns instantly (12 personas ×
9 questions × 2 "models") with no provider call, and carries no field indicating it is seeded. A word-scan of
all three interview screens for `fixture / demo / seeded / pre-generated / not live` returned **zero matches**.

### Root cause
Two separate omissions, not one bug:
1. `interview_service._serialize_interview_job` did not forward `demo_fixture`, `fixture_source` or `judge_model`.
2. `interview-synthesis-section.tsx` hardcoded method claims that are only true of the live Custom Study path,
   and `InterviewRunPayload` had no field through which the client could have known better.

### Regression tests added
Written first, each watched failing before implementation.

| Test | Watched fail as |
|---|---|
| `test_neo_interview_run_discloses_fixture_provenance` | `KeyError: 'demo_fixture'` |
| `test_live_interview_run_is_not_flagged_as_fixture` | guard — validated by temporarily hardcoding `demo_fixture: True`, which produced `assert True is False`, then reverting |
| `interview-provenance.test.ts` × 6 | `TS2307 Cannot find module`, then `TS2339 Property 'groundingScoreCaveat' does not exist` |

The six helper cases cover: fixture flagged as seeded · fixture not credited with dual-model or judge ·
live run described as dual-model with its real judge · absent run not assumed live · score caveat present for
a fixture · score caveat absent for a judged run.

### Files changed
- `apps/api/src/services/interview_service.py` — forward the three provenance fields (+5)
- `apps/api/tests/test_studies_endpoints.py` — two backend tests (+76)
- `apps/web/src/lib/interview-provenance.ts` — **new** pure helper (+68)
- `apps/web/tests/interview-provenance.test.ts` — **new** (+74)
- `apps/web/src/lib/api.ts` — `InterviewRunPayload` gains the three fields (+3)
- `apps/web/src/components/sections/interview-synthesis-section.tsx` — claims derived from provenance (+48/−11)
- `apps/web/tsconfig.test.json` — include the new lib file in the test project

### Fix
The JSX itself is not testable under the current `node:test` setup, so the disclosure **decision** was
extracted into a pure function (`describeInterviewProvenance`) that is TDD'd, leaving the component a thin
render. For a fixture run the section header, banner and "How it works" list now describe what actually
happened, and the grounding score carries *"Derived from persona fit tier — this is not a measure of
agreement between models."* A live run is unchanged.

**Quota was deliberately not changed.** `test_interview_run_counts_against_daily_provider_limit` uses the Neo
fixture path and asserts the second run returns 429, so charging a provider run for a fixture is an existing,
tested contract. Rewriting someone else's test would have conflated disclosure with a separate policy
decision — see Remaining risks.

### Verification
| Check | Result |
|---|---|
| New backend tests | **2 passed** |
| Interview + quota group | **10 passed** |
| Full backend suite | **66 passed, 1 known pre-existing F-02 failure** (baseline 64+1; +2 new) |
| Frontend suite | **42 passed, 0 failed** (was 36) |
| Full project typecheck `tsc --noEmit -p tsconfig.json` | **clean** — the unit suite alone does *not* typecheck JSX, so this was run explicitly |

**Runtime, real API:**
```
demo_fixture   : True
fixture_source : 'generated_fallback'
judge_model    : 'demo/stamp-fixture'
```

**Runtime, rendered UI** — false claims gone, disclosure present:
```
bothModelsInterview      : false     seeded demo disclosed        : true
krippendorff             : false     "No model was called"        : true
dualModelVerification    : false     placeholder names disclosed  : true

STAMP GROUNDING SCORE / 100% / Corpus-level agreement (threshold 67%)
Derived from persona fit tier — this is not a measure of agreement between models.
```

**Commit:** `e332726` on `fix/f-07-interview-fixture-transparency`, cut from `2691642`
(7 files, +269 −11). Not pushed, not merged.

### Remaining risks
1. **Fixture runs still consume provider quota** — deliberately out of scope (see Fix). Worth a follow-up
   decision: quota exists to cap provider spend, and a fixture spends nothing.
2. **Interview Insights (section 12) was not touched.** Its themes are still pre-written English presented as
   *"Mentioned by ~12 interviews"*. The same helper should be applied there.
3. **The underlying shortcut remains.** This makes the fixture honest; it does not make Neo interviews live.
   If the classroom module needs genuinely generated Neo interviews, that is a separate piece of work.
4. **No component test covers the rendered JSX** — the disclosure logic is tested, the rendering was verified
   manually in a browser. A component-test setup would close that gap.


---

## F-06 + F-15 — fabricated and self-contradictory segment ranking

Fixed together: they are two symptoms of one root cause in the same function pair.

### Original behavior
```python
def _compute_strongest_segment(df) -> str:
    segment_scores = _segment_score_table(df)
    if not segment_scores:
        segments = _list_segments(df)
        return segments[0] if segments else "N/A"   # alphabetically first
    return max(segment_scores.items(), key=lambda i: i[1])[0]
```
`_segment_score_table` only scores a segment that has numeric answers for the Neo ids **Q0B / Q1 / Q2**.
For any other survey it scores nothing, and the function returned the **alphabetically first** segment label
as a finding — captioned *"Segment with the strongest overall directional signal in this run"* and injected
into the evidence package as `exec_strongest_segment`, which the summarising model is told not to contradict.

Separately (**F-15**), when exactly one segment scored, `max` and `min` returned the same key, so the same
segment was reported as **both strongest and weakest**.

### Reproduction
QA record: a StudyFlow/FocusPlan study returned `strongest='Balanced Mainstream'` — alphabetically first of
`['Balanced Mainstream','Family Upgraders','Remote Professionals','Wellness-Oriented']` — with
`weakest='N/A'`; a later run returned strongest **and** weakest as the same label.

### Root cause
Ranking requires **at least two scored segments**. With none there is nothing to rank; with one, `max` and
`min` are the same element. Neither case was guarded.

A second, subtler defect: the evidence guard is `if strongest_segment:` — a **truthiness** check. The string
`"N/A"` is truthy, so even the existing "unavailable" sentinel would have injected
*"N/A currently shows the strongest overall interest-oriented pattern."*

### Regression tests added — `apps/api/tests/test_insights_segments.py`
All written first and watched fail.

| Test | Watched fail as |
|---|---|
| `test_strongest_segment_is_unavailable_when_no_scoreable_question_exists` | `assert 'Balanced Mainstream' is None` |
| `test_strongest_and_weakest_are_unavailable_with_only_one_scoreable_segment` | `assert 'Balanced Mainstream' is None` |
| `test_evidence_package_omits_strongest_segment_when_it_cannot_be_computed` | `assert 'exec_strongest_segment' not in {...}` |
| `test_strongest_and_weakest_rank_two_scoreable_segments` | passed from the start — retained as a guard that the Neo path keeps ranking |

### Files changed
- `apps/api/src/adapters/legacy_backend/domain.py` (+15 −7)
- `apps/api/tests/test_insights_segments.py` — **new** (+118)

### Fix
Return `Optional[str]`, and return `None` whenever fewer than two segments scored. Chosen over the existing
`"N/A"` sentinel precisely because `None` is falsy, so the existing evidence guard now does the right thing
with no further change. Both UI render sites already coalesce with `?? "N/A"`, so no frontend change was
needed.

### Verification
| Check | Result |
|---|---|
| New tests | **4 passed** |
| Full backend suite | **68 passed, 1 known pre-existing F-02 failure** (baseline 64+1; +4 new) |
| Neo happy path | two segments still score and rank **distinctly** (`Remote Professionals` / `Wellness-Oriented`) |

**End-to-end, real API** — custom study with non-colliding ids `B1..B4`, three segments present:
```
executive_summary.strongest_segment : None
segment_story.strongest_segment     : None
segment_story.weakest_segment       : None
exec_strongest_segment in evidence  : False
fabricated sentence present         : False
```
Before the fix this exact scenario returned `'Balanced Mainstream'` and injected it into the LLM evidence.

**Rendered UI:** no segment label appears, and no `null` / `undefined` / `NaN` leaks — both sites coalesce to
"N/A".

**Commit:** `15dffc9` on `fix/f-06-segment-fabrication`, cut from `2691642` (2 files, +133 −7).
Not pushed, not merged.

### Remaining risks
1. **This does not fix the ID collision.** A survey using `Q1/Q2` — which the parser *forces*, see **F-14** —
   still scores segments on whatever those questions happen to be. Verified during this work: a StudyFlow
   study with `Q1..Q5` ranked segments on `Q2`, which was coincidentally its interest question. Had `Q2` been
   the price question, segments would have been ranked by price expectation and labelled "strongest
   interest". **F-14 remains the blocker for genuine generalization.**
2. **Detail copy is unconditional.** The card still reads *"Segment with the strongest overall directional
   signal in this run"* beside a value of "N/A". Honest, but it would read better as an explicit
   *"not applicable to this survey"*.
3. **Other Neo-coupled metrics are untouched** — `top_use_case`, `average_interest`, the interest ladder and
   the segment heatmap still key on Neo ids. Those remain under F-06's generalization umbrella.


---

## F-14 — Survey parser rejected semantic question ids

### Original behavior
```python
QUESTION_PATTERNS = [
    re.compile(r"^\s*(?P<id>[A-Za-z]?\d+[A-Za-z]?)\s*[:\.\-]\s*(?P<text>.+)$", re.IGNORECASE),
    re.compile(r"^\s*Question\s*(?P<id>[A-Za-z]?\d+[A-Za-z]?)\s*[:\.\-]\s*(?P<text>.+)$", re.IGNORECASE),
]
```
An id had to be *optional letter → digits → optional letter*. `Q1`, `S3`, `Q0B` matched. `BENEFIT`, `PRICE`,
`CONCERN` could never match, so the upload was rejected:
```
HTTP 400  "No recognizable questions were found in the Markdown file. Expected lines like `Q1:` and `Type:`."
```

**Why this was P0 rather than an inconvenience:** it *forced* every custom study into `Q1..Qn` naming, and the
insights layer reads `Q1/Q2/Q3` as Neo's price-point interest, purchase likelihood and primary intended use.
A researcher could not opt out of the Neo collision, because opting out required ids the parser refused.

### Root cause
The id character class. Compounded by the fact that `_match_question_start` runs on **every line**, before
the metadata check — so the pattern could not simply be widened to any word without turning prose into
questions.

### Regression tests added — `apps/api/tests/test_survey_parser_ids.py`
Characterisation first (safety net for the demo), then RED for the new behaviour.

| Test | Status when written |
|---|---|
| `test_neo_preset_still_parses_its_full_question_set` | passed — locks 32 questions incl. `S3, Q0B, Q1, Q2, Q3, Q5_1, Q5_7` |
| `test_neo_preset_keeps_its_question_types` | passed — locks `single_choice: 8`, `likert: 24` |
| `test_prose_key_value_lines_do_not_become_questions` | passed — guards the widening |
| `test_semantic_question_ids_are_accepted` | **failed** — `assert [] == ['BENEFIT','INTEREST','CONCERN']` |
| `test_semantic_ids_still_resolve_question_types` | **failed** — `KeyError: 'BENEFIT'` |

### Files changed
- `apps/api/legacy_runtime/backend/survey/parser.py` (+8)
- `apps/api/tests/test_survey_parser_ids.py` — **new** (+144)

### Fix
A third pattern for semantic ids, **case-sensitive and all-caps**:
```python
re.compile(r"^\s*(?P<id>[A-Z][A-Z0-9_]{1,31})\s*[:\.\-]\s*(?P<text>.+)$"),
```
All-caps is the safety property, not a style preference: question codes are written in caps, whereas prose
keys (`Note:`, `Mode:`, `Target population:`) are title case and are therefore left alone. Reserved metadata
keys are additionally skipped in `_match_question_start`, so `TYPE:` or `OPTIONS:` cannot introduce a
question. The numeric patterns are tried first, so Neo behaviour is untouched.

### Verification
| Check | Result |
|---|---|
| New tests | **5 passed** |
| Full backend suite | **69 passed, 1 known pre-existing F-02 failure** (baseline 64+1; +5 new) |
| Composed with F-06 (`15dffc9`) | **73 passed, 1 F-02** — the two fixes stack cleanly |

**End-to-end, real API** (with `LEGACY_APP_ROOT` pointed at the vendored copy, matching production):

*Neo preset regression guard* — unchanged:
```
questions: 32   types: {'single_choice': 8, 'likert': 24}
ids: ['S3','Q0B','Q1','Q2','Q3','Q5_1','Q5_2','Q5_3']
```

*The upload that previously returned HTTP 400* — now **HTTP 200**:
```
BENEFIT    single_choice   opts=4
INTEREST   likert          opts=5  min=1 max=5
FEATURES   multi_choice    opts=4
CONCERN    open_text
```

*Insights for that study, with F-06 also applied* — the collision is genuinely avoided:
```
top_use_case      : {"label": "N/A", "share": null}
average_interest  : None
strongest_segment : None      weakest_segment: None
exec_strongest_segment in evidence : False
top_findings      : ['Model comparison']
charts available  : ['model_difference']
```
Compare the QA record's Variant B (`Q1..Q5`), which reported `top_use_case = "$12"`, an interest ladder that
does not exist, and a fabricated strongest segment.

**Commit:** `33ecf21` on `fix/f-14-parser-question-ids`, cut from `2691642` (2 files, +152). Not pushed.

### Remaining risks
1. **The engine exists in two copies and they can diverge — this fix exposed it.** Tests and local dev load
   `NeoSmart-Hackathon-App/backend/...` (the untracked nested checkout, owned by a different GitHub account);
   the Dockerfile ships `apps/api/legacy_runtime/backend/...`. Patching the tracked copy left the two with
   **different SHA-256 hashes**, and the tests initially exercised the unpatched one. The new tests therefore
   load the vendored parser by path. **Local dev will not see this fix until the nested copy is synced, or
   `LEGACY_APP_ROOT` is repointed at `legacy_runtime`** — the latter is what production does and is the
   better default. This is F-01's consequence made concrete.
2. **Numeric is still never inferred** (F-08): `PRICE` parsed as `open_text`. 4 of 5 supported shapes work.
3. **Neo schema still leaks into user-facing copy**: *"Primary use question Q3 was not found."* — F-06's
   generalization umbrella, not fixed here.
4. **Lower-case semantic ids are still rejected** (`benefit.` will not match). Deliberate, to keep prose safe.


---

## F-04b — non-retryable provider errors fabricated a run instead of stopping it

Closes **F-04b** and the first (largest) slice of **F-04**.

### Original behavior
Only `401/403` stopped a run. Every other provider failure fell through to the deterministic
mock-answer generator so the record set stayed complete, and the job was saved `status: "completed"`.
QA reproduced **100% fabrication** on an out-of-credits account and **exactly 50%** when one of two
selected models no longer existed — with the fabricated rows stamped with that model's real name, so the
Model Difference chart compared a live LLM against a seeded heuristic.

### Root cause
`domain.execute_simulation_run` treated every non-auth provider error as recoverable, and
`_extract_provider_error_detail` was called **only** in the auth branch, so the provider's own remedy text
was discarded.

A second, separate defect: the surrounding handler was `except LegacyModuleApiError: raise`, so any *other*
typed `ApiError` raised inside was caught by the broad `except Exception` and rewrapped as
`LegacyModuleApiError` — a 500 that hid an actionable cause behind an apparent crash.

### Statuses, verified against the live API (not assumed)
```
google/gemini-2.0-flash-001  → HTTP 404  "No endpoints found for google/gemini-2.0-flash-001."
totally/does-not-exist       → HTTP 400  "totally/does-not-exist is not a valid model ID"
out of credits               → HTTP 402  "This request requires more credits, or fewer max_tokens…"
openai/gpt-4o-mini           → HTTP 200  (control)
```

### Regression tests added
| Test | Watched fail as |
|---|---|
| `test_execute_simulation_run_fails_fast_when_provider_is_out_of_credits` | `expected the run to fail fast; it returned status='completed' with 2 fabricated records` |
| `test_execute_simulation_run_fails_fast_on_retired_model_id` | same |
| `test_simulation_run_reports_unavailable_not_server_error_for_retired_model` | `assert 500 == 503` |
| `test_execute_simulation_run_still_falls_back_on_transient_provider_errors` | passed from the start — **kept deliberately** as the guard against over-correcting: a 429 must still complete with fallback |

### Files changed
- `apps/api/src/adapters/legacy_backend/domain.py` (+19 −2)
- `apps/api/tests/test_legacy_live_simulation.py` (+95)
- `apps/api/tests/test_studies_endpoints.py` (+38)

### Fix
```python
_NON_RETRYABLE_PROVIDER_STATUSES = frozenset({400, 402, 404})
```
On those, raise `ProviderUnavailableApiError` carrying `_extract_provider_error_detail(result)` — so it
surfaces as **503 provider_unavailable** with a saved failed job, exactly like the existing missing-key path.
Transient statuses keep their fallback. The surrounding handler now re-raises `ApiError` rather than only
`LegacyModuleApiError`.

### Verification
| Check | Result |
|---|---|
| New tests | **4 passed** |
| Full backend suite | **68 passed, 1 known pre-existing F-02 failure** (baseline 64+1; +4 new) |

**End-to-end against the real provider:**
```
A) retired model in the pair   → HTTP 503  provider_unavailable
   "OpenRouter could not run model google/gemini-2.0-flash-001 (HTTP 404): No endpoints found for …"
   (previously: HTTP 200, status "completed", 50% fabricated)

B) both models valid           → HTTP 200  completed
   records 128 · live_answer_rate 0.953 · fallback 6      ← no over-correction
```

**Commit:** `340d482` on `fix/f-04-fail-fast-on-hard-provider-errors`, cut from `2691642`
(3 files, +150 −2). Not pushed.

### Remaining risks — F-04 is NOT closed
1. **Fallback rows still carry no provenance.** `MockResponseRecord` has no `is_fallback` field and the
   synthesized answer is stamped with the real model name, so charts cannot exclude or flag them.
2. **Diagnostics are still not rendered.** `live_answer_rate`, `provider_error_count`,
   `malformed_json_count` and `persona_generation_mode` reach the client and are displayed nowhere.
3. **Silent coercion fallback remains on healthy runs.** Run B above shows `live_answer_rate 0.953` with
   **6 fabricated answers**, zero provider errors — answers the model really returned but that failed exact
   option/range matching. This is the most common fabrication path and is untouched.
4. **429 still degrades quietly.** Correct per the guard test, but a heavily rate-limited run can still
   accumulate large fabricated shares; a live-answer-rate floor would be the complement.


---

## F-04 (second slice) — the run diagnostics were shipped to the client and rendered nowhere

### Original behavior
`SimulationRunDebugSummary` was declared at `apps/web/src/lib/api.ts` and referenced by **zero**
components. Same for `persona_generation_mode` and `transparency_note`. Verified by grep across
`src/components/`: no match for any of them.

So a run whose answers were partly or wholly deterministic filler looked **identical on screen** to a
genuine one, and the default Insights view opened with a reliability read and no caveat.

### Why this is the important half of F-04
The silent coercion path — answers the model really returned that failed exact option/range matching —
produces `provider_error_count: 0` and `malformed_json_count: 0` while still fabricating values. It is
invisible to the fail-fast fix from `340d482`. A healthy two-model Neo run in this session reported:
```
live_answer_rate 0.953 · fallback_answers 6 · provider_error_count 0 · malformed_json_count 0
```
Six fabricated answers, no error of any kind, nothing on screen.

### Regression tests added — `apps/web/tests/run-evidence.test.ts` (7)
Written first; watched fail as `TS2307 Cannot find module '../src/lib/run-evidence'`.

Cases: fully live reads as trustworthy · partly fabricated surfaces the count · zero live is *critical*
not merely cautionary · provider errors and malformed JSON reported separately · an absent summary claims
nothing rather than implying a clean run · heuristic persona mode is **not** described as grounded ·
genuinely grounded mode is.

### Files changed
- `apps/web/src/lib/run-evidence.ts` — **new**, tested pure helper (+133)
- `apps/web/tests/run-evidence.test.ts` — **new** (+77)
- `apps/web/src/components/sections/run-simulation-section.tsx` (+56)
- `apps/web/src/components/sections/insights-section.tsx` (+8) — renders `transparency_note`
- `apps/web/tsconfig.test.json` — include the new lib file

### Verification
| Check | Result |
|---|---|
| Frontend suite | **43 passed** (honest baseline 36 + 7) |
| Full project typecheck | **clean** |

**Rendered UI, real Neo run:**
```
Some answers were fabricated                     95.3% live
6 of 128 answers could not be used from the model and were replaced with deterministic
filler. They are stored under the real model name, so charts include them.

LIVE ANSWERS 122 / 128 · FABRICATED 6 · PROVIDER ERRORS 0 · MALFORMED JSON 0

Rule-based personas (not grounded). Grounding priors were unavailable, so personas came
from deterministic heuristics. Do not describe them as a census-grounded or
representative sample.
```
`transparency_note` now visible in the default Insights view.

**Commit:** `fd0615e` on `fix/f-04-surface-run-diagnostics`, cut from `2691642` (5 files, +279 −1).
Not pushed.

### Verification hazard found while doing this — R-04
`npm run test:unit` is `tsc -p tsconfig.test.json && node --test .test-dist/tests/**/*.js` and **never
cleans `.test-dist`**. A test compiled on a different branch (`interview-provenance.test.js` from the F-07
work) was still executed here even though its source no longer exists on this branch, inflating the count
from 43 to **49**. Deleted or renamed tests keep "passing", and counts across branches are misleading.
Recorded as **R-04**; a one-line `rm -rf .test-dist &&` in the script fixes it, deliberately left out of
this commit to keep it single-purpose.

### Remaining risks — F-04 still not fully closed
1. **Fallback rows still carry no provenance in the data.** The panel reports *how many* were fabricated;
   it cannot say *which*. `MockResponseRecord` has no `is_fallback` field, so charts and exports still
   cannot exclude or mark them. This is the last substantial piece of F-04.
2. **The Result dashboard is still uncaveated** — the panel lives on the Run section; a reader who lands
   directly on Result sees charts with no sourcing note.
3. **No live-answer-rate floor.** A heavily rate-limited run can still accumulate a large fabricated share
   and complete; it is now visible, but nothing blocks it.


---

## F-04 (third slice) — fabricated answers were not identifiable at the row level

### Original behavior
`_generate_live_response_records_with_debug` replaced any answer that failed coercion with a
`generate_mock_answer` value and appended it as an ordinary `MockResponseRecord` — schema-valid and stamped
with the **real provider model name**. Nothing distinguished it. QA could not identify which records were
invented even with full database access and the survey schema.

### Root cause
Provenance was never recorded. The counter (`questions_fallback_to_mock`) knew *how many*, never *which*.

### Regression test added
`test_saved_records_mark_which_answers_were_fabricated` — watched fail as `KeyError: 'is_fallback'`.
Asserts the discarded single-choice answer is flagged, an accepted open-text answer is not, and that the
per-row flags **reconcile with the reported fallback count**.

### Files changed
- `apps/api/src/adapters/legacy_backend/domain.py` (+22 −6)
- `apps/api/tests/test_legacy_live_simulation.py` (+57)
- `apps/web/src/components/sections/run-simulation-section.tsx` (+11 −1)

### Fix
Track a `record_is_fallback` list parallel to `records` in the build loop and merge `is_fallback` into the
serialized rows — both `response_records` and `response_record_preview`. Flagged rows render with an amber
border and a `Fabricated — not from the model` chip.

**Deliberately not added to `MockResponseRecord`.** That schema lives in the legacy tree, which exists in two
copies that can drift; patching one and not the other is exactly how the F-14 parser fix initially appeared
to do nothing. Keeping the flag in the tracked adapter avoids repeating that.

### Verification
| Check | Result |
|---|---|
| New test | **1 passed** |
| Full backend suite | **65 passed, 1 known pre-existing F-02 failure** (baseline 64+1) |
| Frontend suite | **36 passed** · full typecheck **clean** |

**End-to-end, real Neo run:**
```
records 128 · reported fallback 2 · rows flagged 2 · reconciles: True
flagged by question : {'Q30': 2}
flagged by model    : {'openai/gpt-4o-mini': 2}
```
Rendered:
```
RESP_001 · OPENAI/GPT-4O-MINI · Q30 · FABRICATED — NOT FROM THE MODEL
QUESTION: Attention check — To confirm attention, please select "Moderately interested."
```

**Substantive finding this surfaced.** Both fabricated rows were the survey's **attention-check** question.
Its answer failed exact option matching and was replaced with filler — so a data-quality screen built on that
question would have been reading fabricated values and passing respondents that never answered it. This is
the first time the app could show which question was affected.

**Commit:** `901cf3b` on `fix/f-04-fallback-provenance`, cut from `2691642` (3 files, +84 −6). Not pushed.

### Remaining risks
1. **Charts still include fabricated rows.** The flag exists; no chart, mean or distribution excludes or
   annotates them yet. Whether they *should* be excluded is a research decision, not a code one — worth
   putting to Dr. Wang.
2. **Historic runs have no flag.** Saved `result_json` from before this change lacks `is_fallback`; the UI
   treats absent as not-fabricated, which is the safe default but silently under-reports old runs.
3. **The stability-check path** unpacks the flags but does not persist them; its records are unmarked.
4. **Exports** — there is no export feature yet, but when one is added it must carry this flag.


---

## F-13 — Likert charts rendered an empty named scale beside unlabelled numeric buckets

### Correction to the original finding
The QA record said **24 of 24** Likert cards were affected. Measured precisely during this fix: **17 of 24**.
The 7 `Q5_*` barrier-matrix items declare no options, so `_extract_question_option_values` falls back to
numeric labels `"1".."5"`, which *do* match numeric answers — those charts were already correct. The record
conflated "has numeric buckets" with "is broken".

The 17 genuinely broken: `Q0B, Q1, Q2, Q7, Q9A, Q9B, Q10A, Q10B, Q11A, Q11B, Q12A, Q12B, Q13A, Q13B, Q15,
Q16, Q17` — the entire interest ladder and every positioning concept pair, 17 of the survey's 32 questions.

### Original behavior
```
Q1  response_count 6
   Not at all interested   0   0.0%
   Slightly interested     0   0.0%
   Moderately interested   0   0.0%
   Very interested         0   0.0%
   Extremely interested    0   0.0%
   3                       1  16.7%
   4                       5  83.3%
```

### Root cause
`_shape_distribution_rows` keys `counts_by_label` on the answer's **display value**. Models answer Likert
questions numerically; the question declares **named** scale points. `"4"` never matches `"Very interested"`,
so each declared point resolves to 0 and the numerics fall through into the `extras` list.

Data was never lost — counts always reconciled — so this was a presentation defect, not a correctness one.

### Regression tests added — `apps/api/tests/test_likert_distribution.py` (5)
Watched fail as `TypeError: _shape_distribution_rows() got an unexpected keyword argument 'scale_min'`.

Cases: numeric answers land on the declared points · no unlabelled duplicates remain · **an out-of-range
value stays visible** rather than being forced onto the scale · numeric-labelled scales unchanged ·
categorical questions unaffected.

### Files changed
- `apps/api/src/adapters/legacy_backend/domain.py` (+59 −6)
- `apps/api/tests/test_likert_distribution.py` — **new** (+107)

### Fix
`_likert_scale_position_labels` maps a numeric answer to its declared scale point, applied only when the
declared options are genuinely named **and** their count matches the declared range. `scale_min`/`scale_max`
are carried through from the question schema. Extras de-duplicate against the *mapped* label, otherwise a
resolved value is emitted twice — that was caught by the second test on the first GREEN attempt.

Deliberately conservative: an out-of-range value is left alone and stays visible, because that is a data
problem worth seeing.

### Verification
| Check | Result |
|---|---|
| New tests | **5 passed** |
| Full backend suite | **69 passed, 1 known pre-existing F-02 failure** (baseline 64+1; +5 new) |

**End-to-end on an existing saved run** (reused, so no new provider spend):
```
cards with named labels all at ZERO while numerics hold data: 0        (was 17)

Q1 distribution now:
   Not at all interested     count=0  pct=0.0
   Slightly interested       count=0  pct=0.0
   Moderately interested     count=1  pct=25.0
   Very interested           count=3  pct=75.0
   Extremely interested      count=0  pct=0.0
   response_count: 4 | sum: 4
```
No data was migrated — this changes how existing saved records are read.

**Commit:** `ca67ecb` on `fix/f-13-likert-scale-buckets`, cut from `2691642` (2 files, +160 −6). Not pushed.

### Remaining risks
1. **Insights heatmap and means are unaffected** — they compute from raw numeric answers and were always
   correct; only the dashboard distribution was mis-rendered.
2. **Scales whose declared option count does not match `max - min + 1`** are left unmapped, so they will
   still show numeric buckets. Conservative by design, but worth checking against course survey templates.
3. **`_likert_sort_key` ordering of extras** is unchanged; a mixed chart (some mapped, some out-of-range)
   orders named points first, then extras.


---

## F-01 — fresh checkout could not run: broken gitlink

Decision taken: **option (a)** — make `apps/api/legacy_runtime` the canonical runtime for local
development and production, remove the gitlink, end the two-copy drift.

### Original behavior
`NeoSmart-Hackathon-App` was a gitlink (mode `160000`) at commit `0d066c1`, pointing at
`https://github.com/ytun1/NeoSmart-Hackathon-App.git` — **a different GitHub account** — with **no
`.gitmodules`**. A fresh clone produced an empty directory, `LEGACY_APP_ROOT` resolved to nothing, every
`load_module("backend.*")` failed, and the backend suite died at import.
`git submodule update --init` could not help: there was no mapping to read.

### Why it had to be fixed rather than worked around
Production already sidestepped it by vendoring the engine and having the Dockerfile rebuild the old path,
leaving **two copies of the same 56 modules with nothing keeping them in step**. That drift bit this QA pass
directly: the F-14 parser patch applied to the vendored copy appeared to do nothing, because the tests load
the other one. The two files had different SHA-256 hashes.

### Pre-implementation inventory (as instructed)
| Item | Size | Decision |
|---|---|---|
| `backend/` — 17 modules loaded via `load_module` | — | already vendored, byte-identical |
| Neo survey presets (2 `.md`) | 33 K | already vendored |
| AYTM `.docx` | 253 K | **vendored** — a parser test reads it |
| `scripts/` — ACS/AHS/CEX prior pipeline | 232 K | **vendored** — the only copy of the census-grounding pipeline, in a repo this project does not own |
| `realism_targets_*template.json` | 16 K | **vendored** — see below |
| PDFs / pptx source material | **13.5 M** | **not committed** — reference material the runtime never reads; remains in the original repository |

Runtime dependencies confirmed by tracing every `load_module(...)` call and every path the vendored modules
compute internally (`presets.py` → `<root>/Provided Info/…`; health checks → `<root>/data/processed/{priors,lookups}`).

### Two things the flip exposed
1. **`test_analysis_endpoint_returns_summary_and_question_explorer` asserts `realism_scorecard.available
   is True`** — it passed only because tests pointed at the checkout, which had the targets file, while
   **production silently lacked it and returned "targets file not found".** Tests and production disagreed.
   Vendoring the template makes them agree. **Caveat recorded:** the file's own notes say *"Replace with real
   observed distribution from survey summary"* — the targets are placeholders and no realism claim should be
   made from them.
2. **`test_upload_aytm_docx_succeeds_with_fallback_parser` hardcoded the gitlink path** rather than using
   `legacy_app_root`, so it would have broken silently on removal. Now resolves via settings.

### Regression tests added — `apps/api/tests/test_legacy_runtime_self_contained.py` (21)
Watched fail as: *"legacy root … is outside this repository, so a fresh clone cannot populate it"*.

Asserts the configured root is inside the repo and named `legacy_runtime`; that **each of the 17
runtime-loaded modules** is present (parametrised); that the Neo preset resolves; that the DOCX fixture is
vendored; and that the prior-build scripts survived.

### Files changed
47 files. `apps/api/legacy_runtime/**` (vendored additions), `apps/api/tests/conftest.py`,
`test_settings.py`, `test_studies_endpoints.py`, `.env.example`, `Dockerfile`, `render.yaml`, `README.md`,
`Documentation/vercel-render-deployment.md`, `Documentation/invite-only-deployment-runbook.md`, and removal
of the `NeoSmart-Hackathon-App` gitlink.

The Dockerfile no longer reconstructs a second copy — it asserts the engine is present:
```dockerfile
RUN test -d /app/apps/api/legacy_runtime/backend
```
`render.yaml` sets `LEGACY_APP_ROOT=/app/apps/api/legacy_runtime`; `.env.example` uses `./legacy_runtime`.

### Verification
| Check | Result |
|---|---|
| Full backend suite (worktree) | **85 passed, 1 known pre-existing F-02 failure** |
| **Fresh checkout of the commit** — `git archive HEAD`, no gitlink, no symlink, no manual setup | **85 passed, 1 F-02** |

Fresh-tree contents: gitlink **absent**, 56 engine modules, Neo preset, AYTM docx, 34 prior-build scripts,
realism targets, `LEGACY_APP_ROOT=./legacy_runtime`.

Before this commit the same fresh checkout produced `ModuleNotFoundError: No module named 'backend'` and the
entire suite failed to collect.

**Commit:** `83da8c9` on `fix/f-01-canonical-legacy-runtime`, cut from `2691642`
(47 files, +4887 −26). Not pushed.

### Remaining risks
1. **13.5 MB of source PDFs/decks still live only in `ytun1/NeoSmart-Hackathon-App`.** Not runtime
   dependencies, but if that repo becomes unavailable they are lost. Worth archiving deliberately — a shared
   drive or git-lfs — especially for the CARLE deposit.
2. **The Streamlit reference app (`app/`) and `docs/` were not vendored.** Same consideration.
3. **Vendoring the realism template changes production behaviour**: the scorecard becomes "available" where
   it previously reported "targets file not found". No frontend renders it today, so nothing is user-visible,
   but the values derive from placeholder targets and must not be presented as realism evidence.
4. **Provenance/licensing**: the engine now lives in this repository, so the CARLE deposit question
   (**F-10**) becomes concrete — who holds copyright on code originally authored in another account's repo.


---

## F-04 (fourth slice) — fabricated answers excluded from analysis by default

Decision taken: **option (a)** — exclude from charts, means, percentages, rankings and Insights; keep the
records with provenance; show what was excluded.

### Original behavior
Every mean, percentage, distribution and ranking averaged deterministic filler in as though a model had
produced it. Demonstrated in the regression test: three live `5`s beside one fabricated `1` reported a mean
of **4.0** instead of **5.0**.

### Regression tests added — `apps/api/tests/test_fallback_exclusion.py` (6)
Watched fail as `assert 4 == 3`, `KeyError: 'answer_sourcing'`, and `assert 4.0 == 5.0`.

Charts exclude fabricated answers · dataset summary counts live only · the analysis reports what it excluded ·
**fabricated rows remain inspectable and are not deleted** · Insights metrics use live answers only ·
**runs saved before provenance existed are treated as live** so historic results are not erased.

### Fix
`_split_live_and_fallback_records` + `_answer_sourcing_summary`. Analysis and Insights read the live frame;
`records_preview` pages over a separate all-records frame so a reader can inspect exactly what was excluded
rather than only being told a count. Both payloads carry `answer_sourcing`; the Result dashboard renders it
via a tested formatter, amber when anything was excluded.

A run whose answers were **entirely** fabricated no longer renders charts at all — it reports there is
nothing to analyse, because presenting filler as a distribution is worse than presenting nothing.

### Verification
| Check | Result |
|---|---|
| New backend tests | **6 passed** |
| Full backend suite | **92 passed, 1 known F-02** |
| Frontend suite | **39 passed** · typecheck clean |

**End-to-end on a saved run:** charts and means from **126 live**, **2 excluded**, rate **0.9844**, while
`records_preview.total` stayed **128**.

**Commit:** `34d7635` on `fix/f-04-exclude-fallbacks-from-analysis` (7 files, +304 −6). Not pushed.

### Remaining risks
1. **No user toggle to include fabricated rows** — accepted as out of scope per the decision.
2. **The stability-check path** does not persist provenance, so its records are all treated as live.
3. **Exports** do not exist yet; when added they must carry the flag and the sourcing summary.

---

## F-06(b) — generic wording when an insight does not apply

Decision taken: **option (b)** now, option (c) deferred.

### Original behavior
Unavailable insights explained themselves in Neo's vocabulary: *"Primary use question Q3 was not found"*,
*"Barrier matrix items were not found in this run"*, *"Positioning concept pairs…"*, *"Core decision-ladder
questions…"*. A coffee-subscription study was told about a question its author never wrote, implying they
had mis-numbered something.

### Regression tests added — `apps/api/tests/test_insight_unavailable_messages.py` (3)
Watched fail as *"barrier_ranking still explains itself in Neo's vocabulary"* and
*"Neo vocabulary leaked into a Custom Study: 'Q3'"*.

Custom studies use the generic wording · **no Neo vocabulary appears at all** (scanned for `Q3`, `barrier
matrix`, `concept pair`, `decision-ladder`, `Neo`) · **Neo keeps the diagnostic wording**.

### Fix
`_insight_unavailable_message(study_mode, neo_detail)` — Neo gets the specific text, everything else gets
*"This insight is not applicable to this survey."* `study_mode` threaded into the four builders.

**A bug I introduced and caught:** a careless line in my patch script deleted the four chart assignments,
producing `NameError: name 'barrier_ranking' is not defined` and 8 failures across three test files. Repaired
and re-verified; the collateral failures were my patch, not real defects.

### Verification
| Check | Result |
|---|---|
| New tests | **3 passed** |
| Full backend suite | **95 passed, 1 known F-02** |

**End-to-end:**
```
CUSTOM study : all four -> "This insight is not applicable to this survey."
NEO study    : all four -> available   (unchanged)
```

**Commit:** `b60242b` on `fix/f-06-generic-unavailable-messages` (2 files, +124 −12). Not pushed.

### Remaining risks
1. **The underlying coupling is unchanged** — metrics still key on Neo ids. Option (c), declarative semantic
   roles, remains the real fix.
2. **`realism_scorecard`** still says *"Add it to enable automatic Neo realism scoring"*, but it is Neo-gated
   and unrendered, so it cannot reach a custom-study reader.
3. Generic wording is honest but not instructive — it does not tell a researcher what a survey would need to
   make the insight computable. That guidance arrives naturally with option (c).

---

# Reconciliation with `yaza_Aug_work` @ `d340d14` — 20 Aug

The eleven fixes were built on `2691642`. The target branch moved eight commits, two of which rewrite the
same functions. Rebased rather than merged, so the eight land first and the eleven stay readable on top;
one-fix-per-commit history intact. Result: `integration/qa-aug-17-all-fixes` @ `f048fdd`. Pre-rebase state
preserved at `backup/qa-aug-17-pre-rebase` (`19dd733`) and in eleven `fix/*` branches, all pushed.

## Conflicts, and how each was settled

| File | Shape | Resolution |
|---|---|---|
| `apps/api/Dockerfile` | Both rewrote the same `RUN` | Neither side wholesale — see below |
| `apps/api/tests/conftest.py` | Both set `LEGACY_APP_ROOT` to the same tree | Their `API_ROOT`-relative form; ours referenced `WORKSPACE_ROOT`, which they had deleted |
| `apps/api/tests/test_studies_endpoints.py` | Both appended independent tests at the same point (twice) | Kept both sets |

### Dockerfile — not a choice between the two

Theirs reconstructed `/app/NeoSmart-Hackathon-App/` and asserted a prior table existed inside it. Ours
deleted the reconstruction. Taking either alone loses something real: their version keeps the two-copy
drift F-01 removed; ours drops a guard that stops an image shipping without the prior tables, which
matters because persona generation catches a missing-priors error and substitutes heuristic profiles
without failing. Combined: one tree, guard kept, retargeted at `legacy_runtime/data/processed/priors/`.

### `realism_scorecard` — a contradiction, not a conflict

`b3bd4b5` relaxed the assertion to `available is False`, commenting that the benchmark template
*"does not ship in the vendored legacy runtime yet."* F-01 ships it — that is why it was vendored. Git
auto-merged and kept `False`, which would have passed while describing the opposite of what the tree does.
Restored to `True` and verified live: `GET /analysis` returns `realism_scorecard.available: true`.

The `False` version had passed only because the test suite and the deployed image disagreed about which
files existed — the same class of defect F-01 exists to remove.

### Two `build_grounding_priors.py`, not a duplicate

The plan assumed the two `scripts/` locations duplicated each other and one should go. They do not:

- `apps/api/scripts/build_grounding_priors.py` (316 lines) is self-contained, downloads PUMS, and produced
  the four tables committed in `b3bd4b5`.
- `legacy_runtime/scripts/build_grounding_priors.py` (138 lines) is the last stage of the older
  multi-stage pipeline and reads normalized ACS/AHS/CEX inputs that do not ship.

Both kept. Deleting the legacy tree would have destroyed the research pipeline F-01 was vendored to
preserve. Recorded because the shared filename is a real trip hazard.

## F-04b × concurrent dispatch — the reconciliation that mattered

`1c99e92` dispatches every respondent request through a `ThreadPoolExecutor` and only inspects results
afterwards. F-04b raises on 400/402/404. Both merged cleanly **and the result was wrong**: the raise now
sat downstream of a fully drained batch, so a study with a wrong model id or an empty balance still paid
for every call before reporting the error — the exact cost F-04b exists to avoid.

Neither side is at fault and neither can simply win. Settled by checking each response as it lands:

```python
for future in as_completed(pending):
    results[index] = future.result()
    terminal = _terminal_provider_error(results[index], model_name)
    if terminal is not None:
        raise terminal          # finally: executor.shutdown(wait=False, cancel_futures=True)
```

Queued requests are dropped; the few already in flight are left to finish rather than delaying the error,
and their results are discarded. Healthy runs are untouched — results still fold in respondent order, so
output stays deterministic.

**Watched fail first.** With the merged-but-unreconciled version, at 40 respondents and concurrency 4:

```
AssertionError: the run issued 40 of 40 provider calls before stopping --
every result was collected before any status was inspected
```

Measured end to end afterwards (scenario D, 20 respondents, concurrency 8): **13 of 20** calls issued
before the run stopped. The bound is looser than the worker pool because the stub answers instantly and
workers pull queued items faster than the abort propagates; against a real provider the saving is larger.
The property the test asserts is the honest one — the run stops without paying for every respondent.

## Provenance × the teammate's concurrency tests

`test_live_run_concurrency.py` arrived in `1c99e92` unpacking a 2-tuple from
`_generate_live_response_records_with_debug`. Fallback provenance had made it a 3-tuple, so three of their
tests failed with `ValueError: too many values to unpack`. Fixed inside the commit that changed the
signature rather than left for the merge to trip over.

`test_parallel_and_sequential_produce_identical_records` now also compares the flag lists. Provenance is
positional and per-row, so a list that drifted with completion order would mislabel which answers were
fabricated while the records themselves still matched — the assertion that existed would not have caught it.

## Verification on `f048fdd`

```
apps/api  pytest -q          170 passed, 0 failed      (first fully green run of this QA pass)
apps/web  npm run test:unit   56 passed                 (.test-dist cleaned first — R-04)
apps/web  tsc --noEmit        clean
regression-test census        37 introduced by the eleven commits, all still collected
```

`/api/v1/health`: everything `ok` except `google_vision` and `hud_lookups`, both `warn` for missing
optional credentials. `grounding_priors: ok`.

### Fallback scenarios

| | Scenario | Method | Status | Live | Fallback | Provenance | Enters analysis? | Diagnostics shown |
|---|---|---|---|---|---|---|---|---|
| A | Healthy run, valid models | **live** | completed | 64 | 0 | all `is_fallback: false` | n/a — none to exclude | rate 1.0, no warnings, `grounded_priors` |
| B | Every answer off-option | stub | completed | 0 | 128 | all 128 flagged | **no** — analysis refuses | 2 warnings incl. "completed with temporary deterministic fallback for every saved answer" |
| C | Retired model id | **live** | **503 provider_unavailable** | — | — | no run saved as complete | n/a | "No endpoints found for google/gemini-2.0-flash-001" |
| D | HTTP 402 out of credits | stub | **503 provider_unavailable** | — | — | n/a | n/a | provider's own remedy text; **13 of 20** calls issued |

B and D use a local stub because neither can be induced on demand on a funded account — a model cannot be
made to answer off-option, and 402 needs an empty balance. The stub replaces only the provider; routing,
coercion, provenance, exclusion, the job envelope and the diagnostics are all the real code paths. A and C
are genuinely live. No stubbed result is reported here as live.

Scenario B is where **F-17** was found: analysis refuses the run accurately, insights refuses it with the
wrong reason and no sourcing summary.

### Custom Study smoke test

Bootstrapped the Cortado Roasters coffee preset shipped by `ff9e36f`; 4 respondents, 2 models, **128 live
answers, 0 fabricated**, `persona_generation_mode: grounded_priors`. Insights renders, `answer_sourcing`
reports 128/0/1.0, `strongest_segment` correctly `None`.

It also reproduced F-06's residual defect from the repository's own demo data — `Q1` "Category interest"
labelled "Price-point interest", `Q2` "Current spend" labelled "Purchase likelihood" at 0.0, `Q3` "Where
you buy today" labelled "Primary intended use". See the F-06 entry in `05_Bugs_and_Blockers.md`.

---

## F-06 (final slice) — Neo research meaning acquired from question ids

**Branch** `fix/f-06-gate-neo-metrics`, cut from `8ba31ee` (PR #11 merged into `yaza_Aug_work`).
**Commit** `71bbf3b`.

### Root cause

Six insight metrics decided whether they applied by looking for literal ids — `Q1`, `Q2`, `Q3`, `Q0B`,
`S3`, `Q5_*`, `Q9A/Q9B`–`Q13A/Q13B` — and attached Neo's meaning to whatever answered them.
`schema_normalizer.py:49` assigns `f"Q{index}"` to any question that declares no id, so an ordinary
uploaded survey lands on those ids **by default**, not by coincidence.

`b60242b` had passed `study_mode` into four of the builders, but only to choose the *wording* of an
unavailable state. Availability itself still keyed on the ids, so a collision produced `available: true`
with Neo's labels.

Traced through: `build_insights_view` → chart builders → `_build_executive_summary` /
`_build_top_findings` / `_build_segment_story` → `_build_insights_evidence_package` → LLM summary. The
mislabels reached the evidence package, and the summarising model is instructed not to contradict its
evidence. `build_analysis_view` was clean — it calls none of these builders.

Three of the six never received `study_mode` at all: `_build_segment_heatmap`, `_build_executive_summary`
(`average_interest`, `strongest_segment`) and `_build_segment_story` (`weakest_segment`).

### Regression tests added

`tests/test_neo_metric_gating.py`, five tests on a Cortado-shaped fixture. Watched fail first:

```
AssertionError: a coffee-subscription study was described using the Neo meaning 'Price-point interest'
AssertionError: renaming the questions changed what the study was said to show
KeyError: 'message'                     (the chart was available, so it carried no message)
```

Two of the five passed before the fix and had to — they are the guard tests: Neo keeps its metrics, and
generic metrics keep working for a Custom Study. A fix that broke either would have been caught.

Two of my own assertions were **too strict and were corrected, not the product**: a Custom Study
legitimately echoes its *own* question ids back to the researcher (`"Q3: segment differences observed…"`),
so the vocabulary check now targets Neo *phrases*, and the rename check normalizes the researcher's ids
before comparing. Both were test-design errors on my part.

### The fix

`_is_neo_study(study_mode)` plus an early return in each Neo-schema builder. Nothing is substituted for a
Custom Study: `_neo_metric_unavailable()` returns an empty, explicitly unavailable block.

### Before / after, same Cortado preset, 4 respondents, 2 models, 128 live answers

| | Before `8ba31ee` | After `71bbf3b` |
|---|---|---|
| `message_performance` · `use_case_share` · `interest_ladder` · `segment_heatmap` | available, Neo-labelled | unavailable, generic wording |
| `average_interest` | **3.75** — a 1-5 rating averaged with a dollar spend band | `None` |
| findings | Top intended use · Decision ladder · Model comparison | **Model comparison** |
| `model_difference` | available | available — unchanged |

Neo, same session: six charts available, ladder rows `S3` Feasibility · `Q0B` Category interest ·
`Q1` Price-point interest · `Q2` Purchase likelihood, `average_interest` 3.5, four Neo findings. Unchanged.

### Also closed

The realism scorecard's non-Neo message read *"Realism scorecard is shown only for Neo Smart mode."* —
naming a study the reader is not running. Same generic wording now.

### One existing test changed

`test_insights_metrics_use_live_answers_only` asserted `average_interest` for a Custom Study. That value
only ever resolved *through the collision this removes*, so the test moved to Neo mode. The property it
checks — fabricated answers excluded from means — is unaffected and still asserted.

### Verification

```
apps/api  pytest -q          175 passed, 0 failed
apps/web  npm run test:unit   56 passed   (no frontend change; run because the insights shape changed)
apps/web  tsc --noEmit        clean
```

### Remaining risk

The gate stops false claims; it does not give custom surveys their own version of these metrics. A
researcher running a coffee study still gets model comparison and nothing else. Declarative semantic roles
remain the real answer and were deliberately not built here.

---

## F-05 — three quantities, one label

**Commit** `72d2368` on `fix/f-06-gate-neo-metrics` (continued).

### Root cause

A run produces three genuinely different numbers — personas, executions (respondent × model × rerun),
and answer records (executions × questions) — and all three were presented as "responses".

- `total_generated_responses` was always `sample_size`: `run_manager.run_mock_simulation` sets
  `total_generated = config.sample_size`, and `_call_with_supported_kwargs` silently drops the `records`
  kwarg because the function it calls does not accept it. The field ignored models, reruns, questions,
  and whether any provider call succeeded.
- `getCompletedResponseCount` counted distinct `respondent_id`. Mirror mode **deliberately reuses**
  respondent ids across models so the same persona can be compared, so the tile returned N for a run
  that produced N × M.
- `generation_debug["respondents"]` was `len(respondent_model_pairs)` — the execution count under the
  wrong name. Nothing read it, so it was corrected rather than duplicated.

### Regression tests added

`tests/test_run_counts.py` (5) and `tests/run-counts.test.ts` (6). Watched fail first:

```
KeyError: 'run_counts'
AssertionError: a 2-persona x 2-model mirror run produces four completed responses, not two
  assert 2 == 4
```

The reconciliation test is the one that matters: the reported counts must equal what is actually
stored — `answer_records == len(records)`, `executions == distinct (respondent, model)` pairs, and
`executions × questions == answer_records`. A number that cannot be checked against the data is just
another claim.

### Verified live, mirror mode, Neo preset, 2 personas × 2 models × 32 questions

```
run_counts                : {"personas": 2, "executions": 4, "questions": 32, "answer_records": 128}
total_generated_responses : 4          (was 2)
distinct respondent_id    : 2          <- what the tile showed
distinct (respondent, model): 4
analysis total_records    : 128        (agrees)
```

The tile now reads **4** under "Responses", captioned *"2 personas · 4 completed surveys · 128 answers"*.
At the sample size the teaching module uses — 20 personas, 2 models, 32 questions — the old tile showed
**20** for 40 completed surveys and 1,280 stored answers.

### One existing test changed

`test_execute_simulation_run_uses_live_selected_models` asserted `total_generated_responses == 2` while
also asserting 8 saved rows, locking the mis-count in as expected behaviour. It now asserts the full
count block.

### Verification

```
apps/api  pytest -q          180 passed, 0 failed
apps/web  npm run test:unit   62 passed
apps/web  tsc --noEmit        clean
```

### Note on process

The first attempt at this commit used `git add -A` and swept in untracked working files —
`.tours/`, several `Documentation/` drafts, a local database backup, and the `NeoSmart-Hackathon-App`
checkout as an embedded git repository. Caught on the commit output and amended; the files are untracked
again and unchanged on disk. Recorded because the embedded-repo case is exactly the defect F-01 removed.

---

## F-17 — Insights named the wrong cause for an all-fabricated run

**Commit** `627660e`.

### Root cause

`build_insights_view` splits live answers from filler and then tests `if not records:`. For an
all-fabricated run that test is true even though the run holds a full set of records, so it returned the
message written for a run that has not stored anything yet, and omitted `answer_sourcing`.

`build_analysis_view` tests `if not all_records:` first and only then the live subset, which is why it
was accurate. The fix gives insights the same two-step check.

### Regression tests added

`tests/test_insights_all_fabricated.py` (4). Watched fail first:

```
AssertionError: the run holds four records; saying it has none names the wrong cause
KeyError: 'answer_sourcing'
```

One is a guard against over-correcting: a genuinely empty run keeps its own message. And one asserts the
two surfaces agree about the same run, which is the property that was broken.

### Verified live, stub provider returning off-option answers, Neo preset

```
run_counts  {"personas": 2, "executions": 2, "questions": 32, "answer_records": 64}

analysis  available=false  sourcing: live 0 / excluded 64 / rate 0.0
          "Every answer in this run was deterministic filler ... nothing to analyse."
insights  available=false  sourcing: live 0 / excluded 64 / rate 0.0
          "Every answer in this run was deterministic filler ... nothing to summarise."
```

### Two things found while fixing it

- `formatAnswerSourcing` rendered "Built from 0 live answers" — describing a construction that did not
  happen. A run with no live answers now says so instead.
- The Insights unavailable state rendered the message alone, which is exactly where the wrong reason was
  read. It now shows the sourcing summary beside it, so the refusal comes with the numbers behind it.

### Verification

```
apps/api  pytest -q          184 passed, 0 failed
apps/web  npm run test:unit   63 passed
apps/web  tsc --noEmit        clean
```

---

## F-08 (first slice) — ids invented from list positions

**Commit** `e9c51f4`. The upload blocker only; two sub-defects deliberately left open, see
`05_Bugs_and_Blockers.md`.

### Root cause

`_match_question_start` mapped any bare list number `N.` to `QN`. A Google Forms export numbers every
field including the email capture, so `1. Email*` became `Q1` while the survey's own `Q1.` was also `Q1`,
and the validator rejected the file outright. The document is valid; the parser invented the collision.

Separately, `normalize_survey_payload` assigned `Q{index}` to any question that declared no id without
checking what the document already used — the same hazard from the other direction.

### Regression tests added

`tests/test_survey_id_collisions.py` (6). Watched fail first:

```
AssertionError: the upload still collides: ['Q1', 'Q1']
AssertionError: a silent rename is worse than the error it replaces: []
ValueError: Duplicate question ids found: Q1        (the real PDF, end to end)
```

One guards the unchanged case: a survey that names nothing is still numbered `Q1..Qn` exactly as before,
so the fix only moves behaviour where a collision actually exists.

### A regression the suite caught

`test_upload_aytm_docx_succeeds_with_fallback_parser` failed after the parser change. The `.docx`
fallback had been reached only when the primary parser raised on duplicate ids. That was an accident
that correlated with the primary parser having done badly rather than a check that it had — with the
collision gone it "succeeded" and returned **32 questions, all open text**, against the fallback's **39
with a real type mix**, silently. The fallback is now selected on the result.

Worth stating plainly: the fix was correct and still made one path worse, and only an existing test
that asserted *which parser ran* revealed it.

### Verification

```
apps/api  pytest -q          190 passed, 0 failed
```

Upload matrix re-measured; see the F-08 entry in `05_Bugs_and_Blockers.md`.

### What remains

Google Forms PDFs now upload but parse as all open text, so they produce no charts. A brochure with no
questions is still accepted as a survey. Both are recorded rather than half-fixed.

---

## F-03 — migrations applied to a database the app never opens

**Commit** `bcb4626`.

### Root cause

`alembic/env.py` read `os.getenv("DATABASE_URL")`. `AppSettings` loads `apps/api/.env`; alembic did not.
With the URL set only in that file — the documented local setup — alembic used `alembic.ini`'s
`sqlite:///./local-dev.db`, reported success, and created all nine tables in a second database.

The `database_schema` health check added in `7645dfa` is what surfaced it originally, and it worked
exactly as intended.

### The fix

`src/persistence/migration_target.resolve_migration_database_url()` — an exported variable wins, because
that is what Render supplies; otherwise the value comes from the same settings object the application
uses. When neither provides one it raises and names the default it is refusing to use. `alembic.ini`'s
`sqlalchemy.url` is now empty, since a default there is only ever reachable by accident.

A module rather than another line in `env.py` so the resolution can be tested at all.

### Regression tests added

`tests/test_migration_target.py` (5): the exported case production depends on, the `.env` case local
development depends on, a whitespace-only value, the refusal, and that migrations and the app resolve the
same URL. Watched fail first as `ModuleNotFoundError`.

### Verified end to end

`apps/api/.env` temporarily pointed at a temp file, `DATABASE_URL` unset in the environment,
`alembic upgrade head`:

```
the app's database (.env)              9 tables
```

Before this change that database would have had 0 and `local-dev.db` would have had 9.

### Verification

```
apps/api  pytest -q          195 passed, 0 failed
```

README now states which database `alembic upgrade head` targets.

---

## F-16 — Reset Product Details described more than it did

**Commit** `1b46df2`.

### Root cause

`handleClearSavedContext` clears the form and sets `isProductReset`, which stops the re-seed effect
restoring the demo product. It makes no API call, and the flag is `useState` — so the saved section is
untouched and loads again on reload. The message claimed *"Neo content will not return unless you load
the demo examples."*

`2691642` genuinely improved the behaviour: within a session, reset no longer re-seeds Neo defaults. The
copy was then rewritten past what the change delivered.

### Fix chosen, and the one not chosen

Copy, not behaviour. The message now depends on whether a saved product exists: with one it says the
saved version is unchanged, that a reload brings it back, and that saving is what replaces it; with
nothing saved it does not warn about a saved copy that is not there.

Clearing the persisted section through the API is the other option in the finding. It changes what the
button does to a user's data, which is a project-owner decision rather than a QA fix, so it is recorded
rather than taken.

### Regression tests added

`tests/product-reset.test.ts` (4). The one that matters asserts that **no** variant of the message claims
the cleared content will not return — the specific false claim, tested directly rather than by matching
the replacement string.

### Verification

```
apps/web  npm run test:unit   67 passed
apps/web  tsc --noEmit        clean
apps/api  pytest -q          195 passed, 0 failed
```

---

## R-04 — stale compiled tests were still being counted

**Commit** `035520a`. Test-infrastructure hygiene only; no product code.

### Root cause

`npm run test:unit` ran `tsc -p tsconfig.test.json && node --test .test-dist/tests/**/*.js`. `tsc` writes
into `.test-dist` without removing what is already there, and the runner globs the directory rather than
the compiled sources — so a `.js` left behind by a branch that has since been deleted, renamed, or
checked out over still executes and still counts.

This is why an earlier session in this pass reported **49** frontend tests when the branch had **36**.

### Demonstrated before fixing

A file was planted at `.test-dist/tests/ghost.test.js` with no `.ts` source anywhere in the repository:

```
ok 15 - GHOST - a test that exists only in .test-dist
# tests 68
# pass 68
```

It ran, passed, and was counted.

### The fix

```diff
-"test:unit": "tsc -p tsconfig.test.json && node --test .test-dist/tests/**/*.js"
+"test:unit": "rm -rf .test-dist && tsc -p tsconfig.test.json && node --test .test-dist/tests/**/*.js"
```

### Verified from the same stale state

The planted file was left in place and the command run again:

```
# tests 67
# pass 67
ghost file after run: removed
```

67 is the true count. Every frontend figure recorded in this pass from here on comes from a clean build
rather than from a hand-run `rm -rf`.

### Verification

```
apps/web  npm run test:unit   67 passed, 0 failed, 0 skipped
apps/web  tsc --noEmit        clean
apps/api  pytest -q          195 passed, 0 failed
```
