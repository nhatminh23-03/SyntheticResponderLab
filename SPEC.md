# SPEC — Neo Smart Living synthetic-respondent platform (Anderson's lane)

Owner: Anderson Edmond. Written 2026-09-04 from the 2026-09-03 call with Dr. Ann Wang, Yaza Tun
and Minh Nhat Doan (notes: `vault/shared/meetings/2026-09-03-aytm-wang-yaza-minh.md`, learning
`LRN-20260903-050`), plus the 2026-09-01 dev call and Wang's 8/27 minutes.

**Hard deadline: Dr. Yufan Lin runs this with his class Sept 21-23.** Everything in P1 and P5 must
be live before then. P4 can land after, but its *design* gates what we tell Wang on Sept 7.

Test command (must pass before any phase is checked off):

```bash
cd ~/dev/SyntheticResponderLab && npm --prefix apps/web run build \
  && python -m pytest apps/api/tests -q \
  && Rscript analysis/tests/test_all.R
```

---

## Do not touch

- `research/neo_persona_set/**` — Yaza's Census pipeline. It is his lane and it lives on
  `yaza_Aug_work`. Read it, never edit it. If the draw needs to change, ask Yaza.
- `yaza_Aug_work` branch — do not merge to `main` (Wang and Yaza both said not yet, 9/1 [16:20]).
- `apps/api/src/services/demo_interview_fixtures.py` and the `study_mode == "neo_smart"` canned
  branch at `interview_service.py:177-187` — leave in place until P1.4 replaces its callers. Deleting
  it early breaks the existing app flow that Yaza and Minh still demo from.
- The 32-question survey instrument. Wang's 8/27 minutes froze it. No re-wording, no re-ordering.
- Anything under `~/dev/aytm-real-data/neo_smart_living/` — the real 600 responses. Read-only, and
  **never let its content into a prompt.** The whole comparison depends on the synthetic side never
  having seen the real answers.

---

## P0 — Correctness debt (do first, it is small)

- [x] **P0.1** Demo interview sends conversation history so follow-ups are answered as follow-ups.
      Done, commit `757c38b`.
- [x] **P0.2** Fix the `fit_tier` judge bug. `interview_prompt_builder.py:283` falls back to
      `fit_tier="unknown"` when the column is blank, then scores `fit_tier_alignment` against that
      placeholder — one of four grounding dimensions is currently scoring noise. Either drop the
      dimension or score it only when a real tier exists. **Do not** feed `fit_tier` into the
      interview prompt; it is scored after, never before (Ann's section 3).
- [x] **P0.3** Answer Wang's unanswered question from [00:59]: how many households survive the
      screen? Write `analysis/screen_counts.R` that reads the PUMS frame and reports N at each
      screen step (raw → detached single-family → income ≥ $100k ADJINC-adjusted → householder age
      30-65 → weighted draw). Nobody on the team currently knows this number.

## P1 — Student interview section (due Sept 16)

The demo page proved the shape and Wang explicitly wants it kept as **its own section**, not another
step inside the gated study workflow [32:11]. Promote it, do not re-architect it.

- [ ] **P1.1** Move `/demo/interview` to a real route (`/interview`) and add it to the app nav as a
      standalone section. Keep the standalone entry — no audience/product/market/survey/experiment
      gate in front of it.
- [ ] **P1.2** Persona list reads from the backend, not a local CSV path. Add
      `GET /api/v1/personas` serving the 30 fixed personas from the database, seeded from
      `personas-B.csv`. The `DEMO_PERSONA_CSV` env fallback goes away.
- [ ] **P1.3** Free-text question box (already present) plus the suggested-question chips. Student
      leads the interview; the transcript is the artifact.
- [ ] **P1.4** Route the section through the FastAPI interview endpoints
      (`POST /api/v1/studies/{id}/interview/chat`, which exists and has no caller) instead of the
      Next.js route calling OpenRouter directly. The Next.js route stays as the demo fallback until
      this passes.
- [ ] **P1.5** Persist transcripts. New table `interview_turn` (study_id, persona_id, session_id,
      role, text, model, tokens_in, tokens_out, cost_usd, created_at). Every turn is logged with its
      cost — this is what makes P3 and the budget answer possible.
- [ ] **P1.6** Export a session transcript to CSV/markdown so students can hand it in.
- [ ] **P1.7** Show the built prompt behind a toggle (already in the demo). Wang's team used it to
      confirm grounding; keep it.

## P2 — AI-to-AI interview lab (Wang approved [17:50], [32:22])

- [ ] **P2.1** Interviewer model picker and interviewee model picker, independent. Curated list with
      a price-per-1M-token label next to each, cheapest first.
- [ ] **P2.2** Persona-count selector. Floor of 3 (Anderson's stated minimum for a meaningful
      comparison), default 3, ceiling 30.
- [ ] **P2.3** Interviewer agent: given the research brief, asks the next question from the prior
      answer rather than replaying a fixed list. This is the piece that makes it AI-to-AI rather than
      a script.
- [ ] **P2.4** Side-by-side comparison view — same persona, same question, N models — so the
      cheap-vs-expensive difference is visible on screen. This is the pedagogical payload.
- [ ] **P2.5** Post-interview scoring: `fit_tier` and emotional classification, computed **after**
      the transcript exists, displayed with an explicit "scored after the interview, never before"
      label. (Depends on P0.2.)
- [ ] **P2.6** Live cost meter — running total for the session, and a pre-flight estimate before the
      run starts ("this run will cost about $X").

## P3 — Cost control (Yaza's proposal, Wang endorsed [23:02])

Wang is firm that students must never spend their own money [18:43]. Anderson's objection stands and
is recorded: a pure replay "wouldn't really be an app." The resolution is a **cache, not a fixture**.

- [ ] **P3.1** Cache key = hash(persona_id, model, question, prior-turn-hash). A repeated question on
      a repeated persona returns the stored answer for free; a genuinely new question calls the API.
      Students get a live, leading interview; the common paths cost nothing.
- [ ] **P3.2** Pre-warm the cache: batch-run the suggested questions across all 30 personas on the
      cheap model, once, and store. Cost of the warm-up is a one-time line item.
- [ ] **P3.3** Per-class spend cap with a hard stop, and a `NEO_LLM_BUDGET_USD` env kill switch.
- [ ] **P3.4** Measured cost report answering Wang's actual question. **Owed to her, and Anderson
      said "tomorrow" [27:27].** Deliverable: a table of $/interview and $/full-run at three model
      tiers, measured not estimated. Reference points from the call, both recollections not
      measurements: ~$5 for 20 personas on an expensive model, ~$0.50 for 10 personas × 2 samples on
      a cheap one (Minh, [30:35]).

## P4 — Validation (Sept 7-10 with Minh; the R lane)

Wang's design, confirmed on the call. **Three comparisons, not one.**

- [ ] **P4.1** `analysis/` directory, R project, `renv` lockfile. R is at `/usr/local/bin/Rscript`.
- [ ] **P4.2** **Arm A** — hard-screened draw. Apply the existing filters, randomly draw 600, compare
      to the real 600. [12:58]
- [ ] **P4.3** **Arm B** — distribution-matched draw. Draw 600 matched to the *observed demographic
      distribution of the real 600*, via iterative proportional fitting (IPF) against the PUMS frame.
      [13:15] This is the arm that answers Anderson's own filter-mismatch finding: the real panel was
      national and unfiltered, only 21% of it passes our screens, and only 6.7% is Californian.
- [ ] **P4.4** **Arm C** — Yufan's ~300-person convenience sample (students' families and friends).
      Match its demographics, draw 300, compare. [13:46] **Blocked: we do not have this file.** Ask
      Wang for it — she does not know whether Yufan ever sent it.
- [ ] **P4.5** Test battery keyed to question type: t-test for continuous, **Wald test**, chi-square
      for categorical. [14:23] Report effect sizes and CIs, not bare p-values — "not significantly
      different" on n=600 is not evidence of equivalence. Add an equivalence test (TOST) with a
      pre-registered margin so "close enough" is a claim we can actually defend.
- [ ] **P4.6** **Non-LLM baseline arm — this is the piece that removes the 18,000-query problem.**
      See the section below. Implement all five baselines; they are cheap and the comparison is the
      contribution.
- [ ] **P4.7** Interview validation is qualitative by design [15:19]: LLM extracts themes from real
      and synthetic transcripts, then measure theme overlap. Use a fixed codebook and report
      inter-rater agreement between two different judge models — a single judge grading itself is
      not evidence.
- [ ] **P4.8** One reproducible report: `Rscript analysis/run_all.R` → a single HTML with every arm,
      every test, seeds fixed. Wang teaches from this; it has to rebuild from scratch.

## P5 — Class-readiness (before Sept 21)

- [ ] **P5.1** Deploy and share the link — Wang asked for it explicitly so the whole team can click
      through and comment [31:54].
- [ ] **P5.2** Team walkthrough session before Yufan's class [04:31].
- [ ] **P5.3** Seed accounts / no-login path for students. They cannot hit a Clerk wall in a 50-minute
      class.
- [ ] **P5.4** Instructor one-pager: what the section teaches, what to click, what the students
      should notice.
- [ ] **P5.5** Load check — a class of ~30 hitting it at once.

---

## The non-LLM respondent question (P4.6)

Anderson raised this on the call [27:42]: the disease-spread modelling he saw over the summer used
something other than an LLM to simulate a population, and it might be cheaper than 18,000 queries.
That instinct is correct and the literature is settled enough to act on.

**The connection is real.** Agent-based epidemic models do not invent their populations — they build
them from ACS/PUMS microdata using **iterative proportional fitting (IPF)**, exactly the same public
data Yaza's pipeline already reads. Synthesized population databases for US agent-based models
(Wheaton et al.), the SPEW R package, and the spatial-ABM synthetic population work all use this
construction. So the epidemic side gives us a *population generator*, and it is the generator we are
already halfway to owning.

**But a population is not a set of answers.** The step from "here are 600 synthetic people" to "here
is how they answered question 17" is a different literature — and it has just been benchmarked
directly against LLMs. Lukauskas and Šarkauskaitė's psychometric audit runs five non-LLM baselines
against LLM synthetic respondents:

| Baseline | What it does |
|---|---|
| Marginal sampler | Draws each item independently from its empirical distribution |
| Multivariate normal | Fits a Gaussian to standardised responses, preserves covariance |
| **Gaussian copula** | Preserves per-item marginals *and* rank correlations, no normality assumption |
| Stratum mean | Returns the demographic-group average for each respondent |
| k-NN lookup | Averages the five nearest demographic neighbours |

**The Gaussian copula beat every LLM on the sample-driven components** — correlation 0.954 vs 0.522
for the best LLM, reliability 0.986 vs 0.939 — and came within 0.026 of it on the composite score
(0.688 vs 0.714, against a human-vs-human ceiling of 0.825). The authors' reading: most of an LLM's
apparent psychometric fidelity is recoverable from the human covariance structure alone.

**What this means for us, concretely:**

1. The 600×32 comparison does not need 18,000 LLM calls. Run it as a copula at $0, in R, in seconds.
2. Adding the baselines is not a cost dodge, it is **the scientific contribution**. "Our LLM personas
   match the real panel" is weak. "Our LLM personas match the real panel *and beat a Gaussian copula
   on the things a copula cannot do*" is a finding. If the copula wins outright, that is also a
   finding, and a more interesting one for a marketing-research class.
3. It gives the paper its honest frame: LLM personas earn their cost on **open-ended verbatims,
   follow-up reasoning, and novel-stimulus response** — the things a covariance matrix has no access
   to. Spend the LLM budget there and let R do the Likert scores.

**The circularity trap, stated plainly.** A copula fit on the real 600 and then compared to the real
600 proves nothing. The baselines must be fit on held-out data — split the real 600, fit on half,
compare on the other half — or fit on Yufan's 300 and tested on the 600. Design this before running
anything. This is the single easiest way to produce a result that looks great and means nothing.

R packages: `copula` or `synthpop` for generation, `mipfp` for IPF, `survey` for weighted
comparison, `TOSTER` for equivalence testing, `lme4`/`brms` if we go to MRP for small-cell
estimates.

Sources:
- [Synthesized Population Databases: A US Geospatial Database for Agent-Based Models](https://pmc.ncbi.nlm.nih.gov/articles/PMC2875687/)
- [Synthetic population generation with public health characteristics for spatial agent-based models](https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1012439)
- [Copula-Based Approach to Synthetic Population Generation](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4973930/)
- [Plausible but Not Valid: A Psychometric Audit of LLMs as Synthetic Survey Respondents](https://arxiv.org/html/2608.14606)
- [Multilevel Regression and Poststratification case studies](https://bookdown.org/jl5522/MRP-case-studies/introduction-to-mrp.html)
- [Your Next Respondent Might Be an LLM: Guidelines for Using Silicon Samples in Marketing Research](https://www.nim.org/en/publications/detail/using-silicon-samples-in-marketing-research)

---

## Blocked on other people

| Blocks | Who | What we need |
|---|---|---|
| P2 scope, P5.4 | Dr. Yufan Lin (via Wang) | Educational goals for the interview section — what the AI-to-AI run should teach students [19:59] |
| P2.6, P3.3 | Dr. Wang | The actual budget for AI-to-AI research runs and for anything students run in class [18:34] |
| P4.4 | Dr. Yufan Lin (via Wang) | The ~300-person convenience sample file [13:46] |
| P0.2 | Yaza | Confirm the judge-side `fit_tier` fix does not collide with his `RETIRED_COLUMNS` change |

Nothing else in this spec waits on anyone.

---

## Assumptions this build runs on (Anderson, 2026-09-04) — and where to roll back

Wang has not sent the educational goals or the budget. Rather than stall, the build assumes the
following. **Each assumption names the single commit to revert if the real answer differs**, so
nothing here is expensive to undo.

| # | Assumption | If wrong, revert |
|---|---|---|
| A1 | **A student run costs $0.50–$1.00**, whether one student or a group. | The `RUN_BUDGET_USD` constant in `apps/api/src/services/llm_budget.py`. Change the number, nothing else — model tiers, persona counts and question counts all derive from it. |
| A2 | **Educational goal = students learn to structure and conduct an interview, and see that AI can do it credibly.** Wang's own guess on the call [20:30], used until Yufan says otherwise. | Tagged `rollback/A2-educational-goals`. The affected surface is P2.4 (comparison view) and P2.5 (scoring display) — the interview mechanics underneath are goal-independent. |
| A3 | **Cheap models are the default**, expensive ones opt-in per run. Anderson's "students should be token economic and AI-agnostic", which Wang agreed with [21:30]. | The `MODEL_TIERS` table in `apps/api/src/services/model_catalog.py`. |
| A4 | **Total OpenRouter spend for the whole build is capped at $20.** Baseline usage at build start: **$39.32** of $87 credits. Hard ceiling: `total_usage` must never exceed **$59.32**. | Enforced by `scripts/build-loop.sh`, which aborts the loop rather than exceeding it. Not a code path — a build guard. |
| A5 | **Cache-first, live-fallback** rather than pure replay. Students get a real leading interview; repeated paths are free. | `CACHE_MODE` in `apps/api/src/services/interview_cache.py` — set to `replay_only` for the zero-cost mode Yaza proposed, or `off` for always-live. |

Every commit made by the build loop is tagged `build/<task-id>` so any single checkbox can be
reverted without unpicking the rest.
