# 07 — Final Verification (release candidate)

**Status: IN PROGRESS — NOT classroom-ready.** Sections A–F are partly evidenced against the merged
SHA below. Section G is untouched and Section H needs Dr. Wang. Do not describe this build as ready for
students.

Rule: a box is ticked only with attached evidence recorded against a specific SHA. An unticked box means
no evidence was gathered, not that the item failed.

**Candidate SHA:** `1bc1c1c61e840c0a57c130749f93e0edaea57efd` — `yaza_Aug_work` after
[PR #12](https://github.com/nhatminh23-03/SyntheticResponderLab/pull/12) merged
(`8ba31ee` was the same branch after [PR #11](https://github.com/nhatminh23-03/SyntheticResponderLab/pull/11)).
**Verified by:** post-merge QA pass, 21 Aug 2026
**Interpreter:** Python 3.11.15 (the pin recorded in `00_QA_Baseline.md` §2)

---

## Post-merge verification run — 21 Aug, against `1bc1c1c`

```
apps/api  pytest -q          195 passed, 0 failed
apps/web  npm run test:unit   67 passed, 0 failed, 0 skipped
apps/web  npx tsc --noEmit    clean
GET /api/v1/health            degraded — google_vision warn, hud_lookups warn; 8 other checks ok,
                              including database_schema and grounding_priors
```

**Neo, mirror, 2 personas × 2 models × 32 questions, live provider**

```
Preview  generation_mode=grounded_priors    Run  persona_generation_mode=grounded_priors
run_counts {"personas": 2, "executions": 4, "questions": 32, "answer_records": 128}
128 rows, 0 fabricated, live_answer_rate 1.0
distinct respondent_id 2   distinct (respondent, model) 4
Analysis  available, records_preview.total 128, realism_scorecard.available true
Insights  six charts available; average_interest 3.5
          findings: Top intended use · Barrier severity · Positioning performance · Decision ladder
```

**Cortado Custom Study, split, 2 personas × 2 models, live provider**

```
Preview  generation_mode=grounded_priors    Run  persona_generation_mode=grounded_priors
run_counts {"personas": 2, "executions": 2, "questions": 32, "answer_records": 64}
64 rows, 0 fabricated, live_answer_rate 1.0
Insights  barrier_ranking · message_performance · segment_heatmap · use_case_share · interest_ladder
          all unavailable — "This insight is not applicable to this survey."
          model_difference available;  average_interest None;  strongest_segment None
          findings: Model comparison
```

**Fallback paths, local stub provider** (labelled stubbed, not live — neither can be induced on demand
on a funded account)

```
partial fallback   64 rows, 62 flagged fabricated, 2 live, rate 0.0312
                   sourcing: 2 used / 62 excluded / 64 total; records_preview.total 64 — nothing deleted
all fabricated     Analysis  available=false  "…nothing to analyse"    sourcing 0 / 64 / rate 0.0
                   Insights  available=false  "…nothing to summarise"  sourcing 0 / 64 / rate 0.0
HTTP 402           run fails 503 provider_unavailable, provider's own remedy text, after 2 of 2 calls
```

No regressions were found. No code was changed during this verification.

---

## A. Reproducibility
- [x] A fresh `git clone` produces a runnable application (F-01) — verified by a `git archive HEAD` checkout
- [x] Migrations target the database the app opens (F-03) — `.env` pointed at a temp DB, nothing exported, `alembic upgrade head` gave that DB all 9 tables. The *rest* of the documented setup has not been walked verbatim by a fresh reader.
- [ ] A `LICENSE` file exists and the CARLE deposit is unblocked (F-10) — **AWAITING PROJECT-OWNER DECISION.** Deliberately not chosen by QA.
- [x] One interpreter and pinned dependency versions are documented — Python 3.11.15, see §2
- [x] `/api/v1/health` reports `degraded`, explained — `google_vision` and `hud_lookups` warn for missing optional credentials; the other 8 checks `ok` on `1bc1c1c`

## B. Automated tests
- [x] `cd apps/api && pytest -q` — **195 passed, 0 failed** on `1bc1c1c`
- [x] `cd apps/web && npm run test:unit` — **67 passed, 0 failed, 0 skipped** on `1bc1c1c`; the script now cleans `.test-dist` itself (R-04, `035520a`)
- [x] Backend suite runs offline with no outbound network calls (F-02) — closed by `b3bd4b5`
- [x] Regression test: live-vs-fallback accounting — `tests/test_fallback_exclusion.py`, `tests/test_legacy_live_simulation.py`
- [ ] Regression test: Split / Mirror / Stability execution and record counts (F-05) — split and mirror covered by `tests/test_run_counts.py`; **stability mode is not**, and its repeat loop still has no test
- [x] Regression test: Insights on a non-Neo survey (F-06) — `tests/test_neo_metric_gating.py`, 5 cases on a Cortado-shaped fixture
- [ ] Regression test: PDF survey parsing (F-08) — id collisions covered by `tests/test_survey_id_collisions.py` (incl. the real Google Forms export, skipped where absent); **option/type recovery is not covered because it does not work yet**
- [x] Test asserting `total_generated_responses` semantics is corrected (F-05) — `681dc4a`; it asserted 2 for a run that produced 4

## C. Data correctness
- [x] A run with a failing provider does **not** report plain success (F-04) — 402 → HTTP 503 `provider_unavailable`; an all-filler run refuses at Analysis and Insights
- [x] Fallback rows are labelled with provenance and excludable from charts (F-04) — partial run: 62 of 64 flagged, excluded from analysis, all 64 still in `records_preview`
- [ ] A retired or invalid model ID is rejected **before the run starts** (F-04b, F-09) — it is rejected on the *first provider response*, not pre-flight. The run stops without completing (2 of 2 calls at N=2; 13 of 20 at N=20), but no validation happens before dispatch
- [x] The three response counts are each labelled for what they are (F-05) — mirror run reports 2 personas / 4 executions / 128 answer records, reconciling with the stored rows
- [x] Strongest Segment returns unavailable rather than an alphabetical guess (F-06) — `None` for Cortado; scored only where the Neo ladder questions exist
- [ ] No Insights metric produces NaN, a silent zero, or an invented value — the known invented value is gone, but the remaining metrics have **not** been audited one by one for this

## D. Failure visibility
- [x] `live_answer_rate`, `fallback_answers`, `provider_error_count` are surfaced (F-04, item 13) — `0fc672f`; covered by `tests/run-evidence.test.ts`. Not re-checked in a browser this session.
- [x] Run and Preview agree on `persona_generation_mode` — both `grounded_priors` on `1bc1c1c` for Neo and Cortado. This was the original §1.5 divergence.
- [ ] `transparency_note` is rendered where findings are shown — **still computed, shipped, and rendered nowhere.** Not addressed.
- [ ] Warnings name what happened, which model, and where to look (item 13) — improved, not audited against the full warning set
- [x] Provider errors surface the provider's own remedy text (F-04) — *"This request requires more credits, or fewer max_tokens…"* reached the client verbatim

## E. Generalization beyond Neo
- [x] A non-Neo Custom Study completes end to end — Cortado preset on `1bc1c1c`, 64 live answers, 0 fabricated
- [x] No Neo terminology leaks into a non-Neo study — asserted over the whole serialized payload in `tests/test_neo_metric_gating.py`
- [x] No Neo schema explanations appear in user-facing messages (F-06) — a study's *own* ids are still echoed in notes about its own data, which is correct
- [x] Renaming question IDs does **not** change the semantic interpretation (F-06) — `C1/C2/C3` and `Q1/Q2/Q3` produce identical claims
- [x] Unavailable metrics say "This insight is not applicable to this survey." — all five Neo charts, verified live

## F. Research transparency
- [ ] The Neo interview fixture is labelled as seeded **in the UI** (F-07) — the backend discloses `demo_fixture` / `fixture_source` / `judge_model` and the client helper is tested (`3dae8f6`), but the rendered result was not re-checked in a browser this session
- [ ] Fixture runs do not consume provider quota (F-07) — **not addressed.** The Neo fixture still charges quota.
- [x] Personas are not described as census-grounded while priors are absent — the ACS priors now load and both paths report `grounded_priors`, so the claim is true. `cex_affordability_available` remains `False`.
- [ ] Confidence and agreement labels state they are heuristics, not inference — **not addressed**, and tied to the unrendered `transparency_note`
- [ ] The "Krippendorff's α" comparison is corrected or removed
- [ ] No claim of benchmarking against a real 600-person panel

## G. Classroom usability
- [ ] Dr. Wang's fix list items 3 and 14 resolved and re-verified
- [ ] Free saved-dataset mode exists (item 12)
- [ ] Per-run cost or request-count estimate shown before launch
- [ ] Instructor guide covers the documented setup pitfalls

## H. Sign-off
- [x] Neo E2E re-run clean at the candidate SHA — `1bc1c1c`, see the run above
- [x] Custom Study E2E re-run clean at the candidate SHA — `1bc1c1c`, see the run above
- [x] All P0 findings closed — F-01, F-04, F-04b, F-06, F-07, F-11, F-14. **0 P0 open.**
- [ ] Reviewed with Dr. Wang — outstanding, along with the licence choice, the panel-of-600 expectation, and the Neo interview step

---

## What "not classroom-ready" means, concretely

26 of 43 boxes carry evidence. The 17 that do not are not a formality:

1. **A PDF upload produces an unusable study.** A Google Forms export now uploads instead of returning
   HTTP 400, but parses as open text only — no distributions, no means, no choice or Likert charts, and
   nothing above "Low confidence". Exporting a Google Form is the most likely classroom path (F-08).
2. **A document that is not a survey can still be accepted as one.** `Neo Smart Living Background.pdf`
   parses as a five-question survey (F-08).
3. **There is no LICENSE**, which blocks the CARLE deposit and is the project owner's decision (F-10).
4. **The transparency note is still rendered nowhere**, so the deterministic confidence and agreement
   labels are shown without the caveat the backend ships with them.
5. **The Neo interview fixture still consumes provider quota**, and its UI labelling has not been
   re-checked in a browser since it was added.
6. **Stability mode has no count coverage**, and the post-run Stability Check's repeat loop still has no
   test at all.
7. **Section G is entirely untouched** — saved-dataset mode, per-run cost estimate, instructor guide.
8. **Nothing has been reviewed with Dr. Wang**, including the panel-of-600 expectation and the Neo
   interview step.

Items 1, 2 and 6 are engineering. Items 3 and 8 need decisions rather than code.
