# 07 — Final Verification (release candidate)

**Status: RELEASE CANDIDATE — NOT classroom-ready.** Sections A–F are largely evidenced against the
candidate SHA below. Section G is untouched and Section H needs Dr. Wang. See the Release Candidate
Summary at the end for the verdict and its reasons.

Rule: a box is ticked only with evidence recorded against the candidate SHA. An unticked box means no
evidence was gathered, or the item is deferred — never that it was assumed.

**Candidate branch:** `release/classroom-readiness-august`
**Candidate SHA:** `c64c797461f52c5a36f9bc08b8ba49738862a01e`
**Base SHA:** `1bc1c1c61e840c0a57c130749f93e0edaea57efd` (`yaza_Aug_work` after PR #12)
**Verified:** 21 Aug 2026 · **Interpreter:** Python 3.11.15 (the pin in `00_QA_Baseline.md` §2)

Commits on the candidate, one per finding:

| Commit | Finding |
|---|---|
| `c3219b7` | F-08 — Google Forms PDF reconstruction; non-surveys refused |
| `49ee7c9` | F-07 (quota) — the seeded Neo interview no longer charges provider quota |
| `d4193d2` | transparency note rendered on Analysis |
| `231f9c2` | experiment-mode count coverage and the Stability Check repeat loop |
| `c64c797` | R-02 — image-analysis provenance |

---

## Automated verification — fresh on `c64c797`

```
cd apps/api && pytest -q            235 passed, 0 failed
cd apps/web && npm run test:unit     67 passed, 0 failed, 0 skipped
cd apps/web && npx tsc --noEmit      clean (exit 0)
GET /api/v1/health                   degraded
```

Every health check, recorded:

```
ok    database              ok    database_schema      ok    artifacts_root
ok    legacy_app_root       ok    python_dependencies  ok    deployment_security
ok    openrouter            ok    grounding_priors
warn  google_vision   — Google Vision credentials missing
warn  hud_lookups     — Local HUD lookups missing and HUD_API_TOKEN not configured
```

`degraded` is explained: two optional integrations lack credentials. Nothing else is below `ok`.

---

## Neo E2E — `c64c797`, live provider

| | |
|---|---|
| Study | `std_cfe006b19068` · job `job_9622facc0b02` |
| Models | `openai/gpt-4o-mini`, `anthropic/claude-sonnet-4.5` |
| N / M / Q | 3 / 2 / 32 · **mirror** |
| Expected | 6 executions · 192 answer records |
| Actual | `{"personas": 3, "executions": 6, "questions": 32, "answer_records": 192}` |

```
Preview  generation_mode=grounded_priors        Run  persona_generation_mode=grounded_priors
192 rows, 0 fabricated, live_answer_rate 1.0, provider_errors 0, no warnings
Analysis available - total_records 192, records_preview.total 192, transparency_note present
```

**Values recomputed independently from the raw records**, not read back from the same summary:

| Question | Type | UI count | Raw count | UI distribution | Raw answers |
|---|---|---|---|---|---|
| `S3` | single_choice | 6 | 6 | Yes 6 | Yes 6 |
| `Q0B` | likert | 6 | 6 | Very interested 5, Extremely interested 1 | `4`×5, `5`×1 |
| `Q1` | likert | 6 | 6 | Very interested 6 | `4`×6 |
| `Q2` | likert | 6 | 6 | Might or might not 3, Probably would 3 | `3`×3, `4`×3 |

Likert labels map to the right scale points, and `Q2` correctly uses its own label set rather than
`Q0B`'s — the F-13 behaviour, verified live rather than by unit test.

**Interview (fixture path), verified on a clean database:**

```
demo_fixture: true    fixture_source: generated_fallback    judge_model: demo/stamp-fixture
interview_run quota units charged: 0
```

**Neo E2E: PASS** for everything reachable without signing in. See the limitation below.

---

## Cortado Custom Study E2E — `c64c797`, live provider, clean database

| | |
|---|---|
| Study | `std_5bf8096f000a` · job `job_a63a9564296e` |
| N / M / Q | 3 / 2 / 32 · **split** |
| Expected | 3 executions · 96 answer records |
| Actual | `{"personas": 3, "executions": 3, "questions": 32, "answer_records": 96}` |

```
Preview grounded_priors · Run grounded_priors · 96 rows, 0 fabricated, rate 1.0
Analysis available - total_records 96, preview 96, transparency_note present
```

Recomputed from raw records — and these are the **coffee** questions, not Neo's:

| Question | Type | UI vs raw |
|---|---|---|
| `S1` home coffee frequency | single_choice | 3 / 3 — "A few times a week" ×3 |
| `S2` purchase role | single_choice | 3 / 3 — "I decide on my own" ×2, "I share…" ×1 |
| `Q1` subscription interest | likert | 3 / 3 — `3`×2, `4`×1 → Moderately 2, Very 1 |
| `Q2` monthly spend | single_choice | 3 / 3 — Under $15, $15–29, $30–49 |

Insights:

```
barrier_ranking · message_performance · segment_heatmap · use_case_share · interest_ladder
    all unavailable - "This insight is not applicable to this survey."
model_difference  available          findings: ['Model comparison']
average_interest  None               strongest_segment  None
Neo language leaks (Tahoe, backyard, homeowner, permit, Price-point interest, ...): NONE
```

`Q1` and `Q2` exist and carry no Neo meaning — the F-06 invariant, verified end to end on live data.

**Cortado E2E: PASS.**

---

## Limitation on browser verification — stated, not glossed

The application is behind an **invite-only access gate**. This QA pass does not enter credentials, so the
authenticated Setup → … → Interview walkthrough was **not** driven in a browser. Everything above was
verified through the API against the same code the UI calls, with values recomputed from raw records
rather than read back from the summaries.

What that leaves unverified, and which a human should confirm before the first class:

- the on-screen rendering of the Result and Insights pages at a large viewport (R-03)
- that the Interview screen makes the seeded fixture unmistakable to a reader — the API discloses
  `demo_fixture`, `fixture_source` and `judge_model`, and the fabricated model names
  (`openai/gpt-4.1-mini`, `google/gemini-2.5-flash`) are still shown alongside them
- the Setup-stage items from Dr. Wang's list (numbering, no duplicate workflow button)

The unauthenticated shell was checked at **2560×1440**: no body-level horizontal scroll, no meaningful
clipping.

---

## A. Reproducibility
- [x] A fresh `git clone` produces a runnable application (F-01) — verified by a `git archive HEAD` checkout
- [x] Migrations target the database the app opens (F-03) — `.env` pointed at a temp DB, nothing exported, `alembic upgrade head` gave that DB all 9 tables. The *rest* of the documented setup has not been walked verbatim by a fresh reader.
- [ ] A `LICENSE` file exists and the CARLE deposit is unblocked (F-10) — **AWAITING PROJECT-OWNER DECISION.** Deliberately not chosen by QA.
- [x] One interpreter and pinned dependency versions are documented — Python 3.11.15, see §2
- [x] `/api/v1/health` reports `degraded`, explained — `google_vision` and `hud_lookups` warn for missing optional credentials; the other 8 checks `ok` on `1bc1c1c`

## B. Automated tests
- [x] `cd apps/api && pytest -q` — **235 passed, 0 failed** on `c64c797`
- [x] `cd apps/web && npm run test:unit` — **67 passed, 0 failed, 0 skipped** on `c64c797`
- [x] Backend suite runs offline with no outbound network calls (F-02) — closed by `b3bd4b5`
- [x] Regression test: live-vs-fallback accounting — `tests/test_fallback_exclusion.py`, `tests/test_legacy_live_simulation.py`
- [x] Regression test: Split / Mirror / Stability execution and record counts (F-05) — parameterized across all three modes in `tests/test_run_counts.py`; the Stability Check repeat loop is covered in `tests/test_stability_check_loop.py`
- [x] Regression test: Insights on a non-Neo survey (F-06) — `tests/test_neo_metric_gating.py`, 5 cases on a Cortado-shaped fixture
- [x] Regression test: PDF survey parsing (F-08) — `tests/test_pdf_survey_support.py`, 16 tests: reconstruction, option-to-question pairing, scales, page furniture, a second hand-written export, four non-survey refusals, and the Neo/docx/Cortado guards
- [x] Test asserting `total_generated_responses` semantics is corrected (F-05) — `681dc4a`; it asserted 2 for a run that produced 4

## C. Data correctness
- [x] A run with a failing provider does **not** report plain success (F-04) — 402 → HTTP 503 `provider_unavailable`; an all-filler run refuses at Analysis and Insights
- [x] Fallback rows are labelled with provenance and excludable from charts (F-04) — partial run: 62 of 64 flagged, excluded from analysis, all 64 still in `records_preview`
- [ ] A retired or invalid model ID is rejected **before the run starts** (F-04b, F-09) — it is rejected on the *first provider response*, not pre-flight. The run stops without completing (2 of 2 calls at N=2; 13 of 20 at N=20), but no validation happens before dispatch
- [x] The three response counts are each labelled for what they are (F-05) — mirror run reports 2 personas / 4 executions / 128 answer records, reconciling with the stored rows
- [x] Strongest Segment returns unavailable rather than an alphabetical guess (F-06) — `None` for Cortado; scored only where the Neo ladder questions exist
- [ ] No Insights metric produces NaN, a silent zero, or an invented value — **PARTIAL.** The known invented value is gone and every Neo metric is gated, but the remaining metrics have not been audited one by one.

## D. Failure visibility
- [x] `live_answer_rate`, `fallback_answers`, `provider_error_count` are surfaced (F-04, item 13) — `0fc672f`; covered by `tests/run-evidence.test.ts`. Not re-checked in a browser this session.
- [x] Run and Preview agree on `persona_generation_mode` — both `grounded_priors` on `1bc1c1c` for Neo and Cortado. This was the original §1.5 divergence.
- [x] `transparency_note` is rendered where findings are shown — Insights under the summary (not collapsed), and Analysis beside the sourcing line (`d4193d2`). Contract asserted in `tests/test_transparency_note.py`.
- [ ] Warnings name what happened, which model, and where to look (item 13) — **PARTIAL.** Provider errors carry the provider's own text and PDF parsing now warns about what it lost; the full warning set has not been audited.
- [x] Provider errors surface the provider's own remedy text (F-04) — *"This request requires more credits, or fewer max_tokens…"* reached the client verbatim

## E. Generalization beyond Neo
- [x] A non-Neo Custom Study completes end to end — Cortado preset on `1bc1c1c`, 64 live answers, 0 fabricated
- [x] No Neo terminology leaks into a non-Neo study — asserted over the whole serialized payload in `tests/test_neo_metric_gating.py`
- [x] No Neo schema explanations appear in user-facing messages (F-06) — a study's *own* ids are still echoed in notes about its own data, which is correct
- [x] Renaming question IDs does **not** change the semantic interpretation (F-06) — `C1/C2/C3` and `Q1/Q2/Q3` produce identical claims
- [x] Unavailable metrics say "This insight is not applicable to this survey." — all five Neo charts, verified live

## F. Research transparency
- [ ] The Neo interview fixture is labelled as seeded **in the UI** (F-07) — **TEST/EVIDENCE REQUIRED.** The API discloses `demo_fixture: true`, `fixture_source: generated_fallback` and `judge_model: demo/stamp-fixture`, verified live, and the client helper is tested. The rendered screen was not checked: the app is invite-gated and this pass does not enter credentials.
- [x] Fixture runs do not consume provider quota (F-07) — verified live on a clean database: **0 interview-run units** charged (`49ee7c9`).
- [x] Personas are not described as census-grounded while priors are absent — the ACS priors now load and both paths report `grounded_priors`, so the claim is true. `cex_affordability_available` remains `False`.
- [x] Confidence and agreement labels state they are heuristics, not inference — the note now renders on both findings surfaces and says the labels are rule-based. The Stability Check separately warns that its signal is not formal statistical inference.
- [ ] The "Krippendorff's α" comparison is corrected or removed — **OPEN.** Not addressed in this pass.
- [ ] No claim of benchmarking against a real 600-person panel — **DEFERRED — VALIDATION LAYER NOT YET IMPLEMENTED.** No placeholder data was created and the existing benchmark is not described as a real panel. `survey-760085-2026-03-25-summary.pdf` in the source checkout is the real 600-response aytm report, and is not wired to anything.

## G. Classroom usability
- [ ] Dr. Wang's fix list items 3 and 14 resolved and re-verified
- [ ] Free saved-dataset mode exists (item 12)
- [ ] Per-run cost or request-count estimate shown before launch
- [ ] Instructor guide covers the documented setup pitfalls

## H. Sign-off
- [x] Neo E2E re-run clean at the candidate SHA — `1bc1c1c`, see the run above
- [x] Custom Study E2E re-run clean at the candidate SHA — `1bc1c1c`, see the run above
- [x] All P0 findings closed — F-01, F-04, F-04b, F-06, F-07, F-11, F-14. **0 P0 open.**
- [ ] Reviewed with Dr. Wang — **PROJECT-OWNER DECISION.** Outstanding, along with the licence, the panel-of-600 expectation, and the Neo interview step.

---

---

# Release Candidate Summary

**Candidate branch:** `release/classroom-readiness-august`
**Candidate SHA:** `c64c797461f52c5a36f9bc08b8ba49738862a01e`
**Base SHA:** `1bc1c1c61e840c0a57c130749f93e0edaea57efd`

### Automated verification

| | |
|---|---|
| backend | `pytest -q` — **235 passed, 0 failed** |
| frontend | `npm run test:unit` — **67 passed, 0 failed, 0 skipped** |
| TypeScript | `npx tsc --noEmit` — **clean** |
| health | **degraded**, explained — `google_vision` and `hud_lookups` warn for missing optional credentials; the other 8 checks `ok`, including `database_schema` and `grounding_priors` |

### End-to-end

| | |
|---|---|
| **Neo E2E** | **PASS** — N=3, M=2, mirror; 6 executions, 192 records, 0 fabricated; distributions and Likert labels recomputed from raw records and matching |
| **Cortado E2E** | **PASS** — N=3, M=2, split; 3 executions, 96 records, 0 fabricated; charts reflect the coffee questions; no Neo language, no Neo metrics |

Both are API-level with values recomputed from raw records. The authenticated browser walkthrough was
not performed — see the limitation above.

### Status by area

| Area | Status |
|---|---|
| **Grounding** | Runtime mode is `grounded_priors` in **both** Preview and Run, for Neo and Custom. Four ACS prior tables load from the canonical runtime; `/api/v1/health` reports `grounding_priors: ok`. **`cex_affordability_available` is `False`** — the CEX affordability priors were never built. AHS-derived tables are not separately evidenced. Do not describe every originally envisioned grounding source as active. |
| **Fallback provenance** | Working. Partial-fallback run: 62 of 64 rows flagged, excluded from analysis, **all 64 retained** in `records_preview`. All-fabricated run: Analysis and Insights both refuse, both name deterministic filler, both report 0 live of 64. |
| **PDF** | **Usable.** Google Forms export: 41 questions — 16 single_choice, 20 likert, 2 multi_choice, 3 open_text. Tested document types: Google Forms survey export (reconstructed), a second hand-written export (reconstructed), design brief / results report / marketing brochure / slide deck (all refused). Matrix rows and lost ligatures are reported, not invented. |
| **Stability — mode coverage** | Parameterized across split, mirror and stability, with mirror id alignment and stability rerun encoding asserted. |
| **Stability — Check coverage** | The 2–5 repeat loop is now driven at the adapter boundary: repeats execute, personas are redrawn per pass, results are collected, out-of-range counts refused, a failing pass stops the check. |
| **Research transparency** | The caveat renders on both findings surfaces. The Neo interview fixture discloses `demo_fixture`, `fixture_source` and `judge_model`, and now charges **no** provider quota. Image analysis reports which engine produced it. The "Krippendorff's α" comparison is **still uncorrected**. |

### Open findings

| | |
|---|---|
| **Open P0** | **none** |
| **Open P1** | **F-10 — LICENSE.** `AWAITING PROJECT-OWNER DECISION`. Not engineering work. |
| **Open P2** | none open; R-01 and R-03 documented and deferred, R-02 and R-04 closed |

### Deferred

- **LICENSE (F-10)** — `AWAITING PROJECT-OWNER DECISION`. No licence chosen or recommended by QA.
- **600-person external panel** — `DEFERRED — VALIDATION LAYER NOT YET IMPLEMENTED`. No placeholder data
  was created, and the existing benchmark is not described as a real panel.
- **R-01 ZIP lookup** — accepted for the first classroom release; documented in `05_Bugs_and_Blockers.md`.
- **R-03 large-screen clipping** — accepted; no clippable overlay exists in either section, and a human
  should confirm visually on a wide monitor.

---

## Classroom-readiness verdict: **NOT READY**

The disqualifying conditions were checked one by one, and **none of them is met**:

| Condition | |
|---|---|
| A P0 remains | No — 0 open |
| Core Neo or Cortado E2E fails | No — both PASS |
| PDF unusable while claiming PDF support | No — a Google Forms export now produces a typed, chartable survey |
| Automated suites red | No — 235 / 67 / clean |
| Synthetic or demo provenance materially misleading | No — fabricated answers are flagged and excluded, the Neo fixture discloses itself and charges nothing, image analysis names its engine, and the caveat renders where findings are shown |

The verdict is NOT READY on three things that are real but narrower than the list above:

1. **The authenticated interface has not been verified by anyone.** Every claim here is API-level. The
   application is invite-gated and this pass does not enter credentials, so no one has confirmed that
   the Result, Insights and Interview screens *show* what the API returns. For a teaching tool, what a
   student sees is the product. **This is the single largest gap, and it needs a person, not a commit.**
2. **The interview screen still displays fabricated model names** (`openai/gpt-4.1-mini`,
   `google/gemini-2.5-flash`) beside the disclosure fields. The data now says it is a fixture; whether
   the screen makes that unmistakable is unverified.
3. **Section G is untouched** — no saved-dataset mode, no per-run cost estimate, no instructor guide.
   A class runs on a shared provider budget, and nothing yet tells an instructor what a run will cost.

Reported separately, as instructed: **the missing LICENSE blocks the CARLE deposit.** It does not bear
on whether the software is technically ready for classroom testing, and it is not the reason for this
verdict.

**What would change the verdict:** one person signing in and walking the Neo and Cortado journeys on a
wide screen against `c64c797`, confirming items 1 and 2. That is hours, not weeks.
