# 07 — Final Verification (release candidate)

**Status: NOT STARTED.** Nothing below is passed. This is the gate for declaring the build classroom-ready.

Rule: a box is ticked only with attached evidence (command output, API response, screenshot, or test run) recorded against a specific SHA.

**Candidate SHA:** `f048fdd` on branch **`integration/qa-aug-17-all-fixes`** (rebased onto `yaza_Aug_work` @ `d340d14`; the pre-rebase stack is preserved at `backup/qa-aug-17-pre-rebase` @ `19dd733`)
**Verified by:** QA pass, 20 Aug 2026 (composition verified; the checklist below is still ungated)
**Date:** 2026-08-20

---

## Where to run everything

`integration/qa-aug-17-all-fixes` (`19dd733`) is the only branch that contains all eleven fixes. It is
built from `2691642` and contains, in dependency order:

| # | Commit | Fix |
|---|---|---|
| 1 | `83da8c9` | F-01 canonical legacy runtime (must be first — it moves `LEGACY_APP_ROOT` and rewrites `conftest.py`) |
| 2 | `fd419c9` | F-04 per-row fabrication provenance |
| 3 | `34d7635` | F-04 exclude fabricated answers from analysis |
| 4 | `b60242b` | F-06(b) generic unavailable-insight wording |
| 5 | `eb591c1` | F-11 atomic daily quota (`599eccf`) |
| 6 | `d5cf114` | F-04b fail fast on non-retryable provider errors (`340d482`) |
| 7 | `f19ca91` | F-04 surface run diagnostics in the UI (`fd0615e`) |
| 8 | `3320c55` | F-07 interview fixture provenance (`e332726`) |
| 9 | `611b551` | F-06(a) stop inventing a strongest segment (`15dffc9`) |
| 10 | `5c7853a` | F-13 Likert counts on declared scale points (`ca67ecb`) |
| 11 | `19dd733` | F-14 semantic survey question ids (`33ecf21`) |

Commits 5–11 were cherry-picked, so their SHAs differ from the originals; the original is in brackets.
`901cf3b` is **deliberately absent** — it is the same change as `fd419c9`, which was rebased onto F-01.

Three cherry-picks conflicted. All three were the same benign shape — both sides appended independent
tests at the same point in a file — and were resolved by keeping both:
`apps/api/tests/test_legacy_live_simulation.py`, `apps/api/tests/test_studies_endpoints.py`,
`apps/web/tsconfig.test.json` (all three new `src/lib` entries kept).

**Composition evidence, 20 Aug:**

```
apps/api  pytest -q          170 passed, 0 failed   (on f048fdd; F-02 is closed upstream)
apps/web  npm run test:unit   56 passed             (.test-dist cleaned first — see R-04)
apps/web  tsc --noEmit        clean
```

The pre-rebase figures were 116 passed / 1 failed and 52 frontend tests. The single failure was F-02,
which `b3bd4b5` closed.

All **36** regression tests introduced by the eleven fixes are collected and passing on this branch —
verified by extracting every `+def test_*` from the eleven commits and diffing against `pytest --collect-only`.

**Before running it, update your local `apps/api/.env`.** It is untracked, so it survives the branch
switch, and it still points `LEGACY_APP_ROOT` at the nested `NeoSmart-Hackathon-App` checkout. Left as-is
it re-creates exactly the two-copy drift F-01 removed, and F-14 will appear not to work because `33ecf21`
patched `legacy_runtime/backend/survey/parser.py`, not the nested copy. Set:

```
LEGACY_APP_ROOT=./legacy_runtime
```

---

## A. Reproducibility
- [x] A fresh `git clone` produces a runnable application (F-01) — verified by a `git archive HEAD` checkout
- [ ] Documented local setup works verbatim, including migrations (F-03)
- [ ] A `LICENSE` file exists and the CARLE deposit is unblocked (F-10)
- [x] One interpreter and pinned dependency versions are documented — Python 3.11.15, see §2
- [x] `/api/v1/health` reports `degraded`, explained: `google_vision` and `hud_lookups` warn for missing optional credentials; everything else `ok`

## B. Automated tests
- [x] `cd apps/api && pytest -q` — 170 passed, 0 failed on `f048fdd`
- [x] `cd apps/web && npm run test:unit` — 56 passed on `f048fdd` (clean `.test-dist`)
- [x] Backend suite runs offline with no outbound network calls (F-02) — closed by `b3bd4b5`
- [ ] Regression test: live-vs-fallback accounting
- [ ] Regression test: Split / Mirror / Stability execution and record counts (F-05)
- [ ] Regression test: Insights on a non-Neo survey (F-06)
- [ ] Regression test: PDF survey parsing (F-08)
- [ ] Test asserting `total_generated_responses` semantics is corrected (F-05)

## C. Data correctness
- [ ] A run with a failing provider does **not** report plain success (F-04)
- [ ] Fallback rows are labelled with provenance and excludable from charts (F-04)
- [ ] A retired or invalid model ID is rejected before the run starts (F-04b, F-09)
- [ ] The three response counts agree, or each is labelled for what it is (F-05)
- [ ] Strongest Segment returns "unavailable" rather than an alphabetical guess (F-06)
- [ ] No Insights metric produces NaN, a silent zero, or an invented value

## D. Failure visibility
- [ ] `live_answer_rate`, `fallback_answers`, `provider_error_count` are visible in the UI (F-04, item 13)
- [ ] `persona_generation_mode` is visible, and Run and Preview agree
- [ ] `transparency_note` is rendered where findings are shown
- [ ] Warnings name what happened, which model, and where to look (item 13)
- [ ] Provider errors surface the provider's own remedy text (F-04)

## E. Generalization beyond Neo
- [ ] A non-Neo Custom Study completes end to end
- [ ] No Neo terminology (Tahoe, backyard, permit, homeowner) leaks into a non-Neo study
- [ ] No Neo question-ID strings appear in user-facing messages (F-06)
- [ ] Renaming question IDs does **not** change the semantic interpretation (F-06)
- [ ] Unavailable metrics say "not applicable to this survey"

## F. Research transparency
- [ ] The Neo interview fixture is labelled as seeded in the UI (F-07)
- [ ] Fixture runs do not consume provider quota (F-07)
- [ ] Personas are not described as census-grounded while priors are absent
- [ ] Confidence and agreement labels state they are heuristics, not inference
- [ ] The "Krippendorff's α" comparison is corrected or removed
- [ ] No claim of benchmarking against a real 600-person panel

## G. Classroom usability
- [ ] Dr. Wang's fix list items 3 and 14 resolved and re-verified
- [ ] Free saved-dataset mode exists (item 12)
- [ ] Per-run cost or request-count estimate shown before launch
- [ ] Instructor guide covers the documented setup pitfalls

## H. Sign-off
- [ ] Neo E2E re-run clean at the candidate SHA
- [ ] Custom Study E2E re-run clean at the candidate SHA
- [ ] All P0 findings closed or explicitly accepted in writing
- [ ] Reviewed with Dr. Wang
