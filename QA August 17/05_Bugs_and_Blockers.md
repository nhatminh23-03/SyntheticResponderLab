# 05 — Bugs and Blockers

**Target:** `yaza_Aug_work` @ `7645dfa` · baseline `main` @ `1cc5ace` · Python 3.11.15
**Status vocabulary:** `OPEN` · `OPEN (new in target commit)` · `FIXED+VERIFIED` (requires a code change **and** re-verification) · `NOT A FEATURE`
**Nothing in this file is marked fixed.** No application behaviour has been modified.

Severity: **P0** blocks classroom use or invalidates research output · **P1** important, materially misleads or obstructs · **P2** polish.

---

## Summary table

| ID | Title | Sev | Status | Blocks classroom? | Regression test? |
|---|---|---|---|---|---|
| F-01 | Fresh checkout cannot run — broken gitlink | **P0** | **FIXED+VERIFIED** (`83da8c9`) | ~~Yes~~ | **Yes** |
| F-02 | Backend test regression + non-hermetic suite | P1 | **FIXED UPSTREAM+VERIFIED** (`b3bd4b5`) — suite is hermetic and fully green on `f048fdd` | ~~No~~ | **Yes** |
| F-03 | Alembic migrates the wrong database locally | P1 | OPEN | No (onboarding) | No |
| F-04 | Fully fabricated run reports success | **P0** | **FIXED+VERIFIED** (`340d482`, `fd0615e`, `901cf3b`, `34d7635`) — hard errors stop the run, diagnostics render, rows carry provenance, and fabricated answers are excluded from analysis by default | **Yes** | Partial |
| F-04b | Retired model ID silently fabricates its half | **P0** | **FIXED+VERIFIED** (`340d482`) | ~~Yes~~ | **Yes** |
| F-05 | Three conflicting "responses" counts | P1 | **FIXED+VERIFIED** (`72d2368`) — personas, executions and answer records named separately | ~~Yes~~ | **Yes** |
| F-06 | Insights fabricates Strongest Segment; Neo `Q*` coupling | **P0** | **FIXED+VERIFIED** (`15dffc9`, `b60242b`, `71bbf3b`) — fabrication closed, Neo wording removed, and Neo metrics now gated to Neo studies | ~~Yes~~ | **Yes** |
| F-07 | Neo interview fixture undetectable by any client | **P0** | **FIXED+VERIFIED** (`fix/f-07-interview-fixture-transparency`, `e332726`) | ~~Yes~~ | **Yes** |
| F-08 | PDF parser inverted; markdown format sensitivity | P1 | **PARTIALLY FIXED** (`e9c51f4`) — the upload blocker is closed; option recovery and non-survey acceptance remain | ~~Yes~~ | **Yes** |
| F-09 | Fallback model catalog contains a retired model | P1 | **FIXED UPSTREAM+VERIFIED** (`b3bd4b5`) | ~~No~~ | Covered by F-04b scenario C |
| F-10 | No LICENSE file | P1 | OPEN | No (blocks CARLE deposit) | N/A |
| F-11 | Concurrent first-of-day request 500s (usage-counter race) | **P0** | **FIXED+VERIFIED** (`fix/f-11-quota-race`) | ~~Yes~~ | **Yes** |
| F-12 | Mode-card selected state 1.61:1, no `aria-pressed` | P1 | **FIXED upstream in `2691642`** (re-measured 9.76:1 + `aria-pressed`) | ~~No~~ | No |
| F-13 | Likert charts show empty named scale + unlabelled numeric buckets | P1 | **FIXED+VERIFIED** (`ca67ecb`) — scope corrected to **17 of 24**, not 24 | ~~Yes~~ | **Yes** |
| F-14 | Parser rejects non-numeric question IDs — forces the Neo `Q*` collision | **P0** | **FIXED+VERIFIED** (`33ecf21`) | ~~Yes~~ | **Yes** |
| F-15 | Strongest and weakest segment can be the same segment | P1 | **FIXED+VERIFIED** (`15dffc9`) | ~~Yes~~ | **Yes** |
| F-16 | Reset Product Details claims Neo content will not return — untrue after reload | P1 | OPEN (new in `2691642`) | No | No |
| F-17 | Insights explains an all-fabricated run as "no response records yet" | P1 | **FIXED+VERIFIED** (`627660e`) | ~~No~~ | **Yes** |
| R-01 | Undocumented third-party runtime dependency (`api.zippopotam.us`) | P2 | OPEN (new in `2691642`) | Possibly (locked-down networks) | No |
| R-02 | Image analysis has no provenance: Vision vs `gpt-4o-mini` indistinguishable | P2 | OPEN (new in `2691642`) | No | No |
| R-03 | `lg:overflow-hidden` on scrollable sections may clip overlays at ≥lg | P2 | OPEN (new in `2691642`) | No | No |
| R-04 | `npm run test:unit` never cleans `.test-dist`, so stale compiled tests still run | P2 | OPEN (found during F-04 work) | No (undermines test trust) | No |

**Counted against the combined tree `f048fdd`** (`integration/qa-aug-17-all-fixes`, eleven fixes rebased
onto `yaza_Aug_work` @ `d340d14`). Commit SHAs below are the rebased ones; the pre-rebase branch is
preserved at `backup/qa-aug-17-pre-rebase`.

**Open: 0 P0 · 4 P1 · 4 P2** as of `e9c51f4` (21 Aug). F-08 is partial, not closed.

- **P0 — none.** F-06 was the last one; its third and final defect closed in `71bbf3b`.
- **P1 open** — F-03, F-08 (partial), F-10, F-16. (F-05 closed in `72d2368`, F-17 in `627660e`.)
- **P2 open** — R-01, R-02, R-03, R-04.

Closed in this pass and verified on `f048fdd`: F-01 (`a3e6d8a`), F-04 (`2fcbea6`, `7b132c4`, `0fc672f`),
F-04b (`98f08fe`), F-07 (`3dae8f6`), F-11 (`8ca47ea`), F-13 (`353b01a`), F-14 (`f048fdd`), F-15 (`b1a7841`).
Closed upstream and verified here: F-02 and F-09 (`b3bd4b5`), F-12 (`2691642`).

**F-17 is new**, found while verifying the combined tree rather than inherited from the original pass.

The backend suite on `f048fdd` is **170 passed, 0 failed** — the first fully green run in this QA pass,
because F-02 was the only red test and it is now closed. Frontend **56 passed**, typecheck clean.

(F-04 and F-04b are related but distinct failure modes and are counted separately.)

---

## F-01 — A fresh checkout cannot run the application
**Severity P0 · OPEN · blocks classroom use · no regression test**

**Reproduction.** `git worktree add <path> 7645dfa` (or `1cc5ace`), then `ls NeoSmart-Hackathon-App/`.

**Evidence.** The directory is **empty**. `git ls-files -s NeoSmart-Hackathon-App` → `160000 0d066c1ddc963e562cc699a6a43f2d1e91c46828 0` (a gitlink). The nested repo's remote is **`https://github.com/ytun1/NeoSmart-Hackathon-App.git` — a different owner**. `git config -f .gitmodules --list` → *"No such file or directory"*, so `git submodule update --init` has no mapping to read.

**Consequence.** `LEGACY_APP_ROOT` points there; every simulation, persona and analysis call loads `backend.*` from it. A new contributor cloning the repo gets a non-running application, and the entire backend test suite fails at import. This is the concrete answer to Dr. Wang's "what would a new person need to know" — and it puts part of the runtime outside this project's ownership for the CARLE deposit.

**Root component.** Repository structure / build packaging.

**Note.** `main` already mitigates the *deployed* path by vendoring `apps/api/legacy_runtime/` (byte-identical at this SHA) and reconstructing the path in the Dockerfile. **Local development is not mitigated.**

---

## F-02 — Backend test regression, and the suite is no longer hermetic
**Severity P1 · FIXED UPSTREAM in `b3bd4b5` · verified on the combined tree `f048fdd`**

> **Closed 20 Aug, both halves.** `conftest` now passes `_env_file=None`, so the developer's `.env` no
> longer leaks into tests, and `test_product_provider_gaps_fail_clearly` was replaced by
> `test_product_url_autofill_falls_back_without_openrouter_key`, which monkeypatches the scraper instead
> of reaching `example.com`. On the combined tree the whole backend suite is **170 passed, 0 failed** —
> the first fully green run recorded in this pass. The original finding is kept below unchanged.

**Reproduction.** `cd apps/api && pytest -q`

```
main  1cc5ace  →  64 passed
yaza  7645dfa  →  1 failed, 64 passed        (65 total; the commit added 1 health test)

tests/test_studies_endpoints.py::test_product_provider_gaps_fail_clearly
AssertionError: assert 'OPENROUTER_API_KEY is required' in 'URL returned HTTP 404'
```

**Attribution is conclusive:** `test_studies_endpoints.py` is **byte-identical** between the two commits (`diff -q` → no difference). Only the source changed.

**Cause.** `7645dfa` moved the credential check in `product_url_autofill` from *before* the page fetch to *after* it, so a keyless request now scrapes first and fails on the fetch instead.

**Second-order defect.** `backend/scraper.py::scrape_product_page` does `requests.get(url, timeout=15)`. The test URL `https://example.com/product` is now **really fetched** (confirmed: returns a genuine 404). Timing for the same single test: main **1.02 s** → yaza **1.49 s**. On a runner without egress this blocks to the 15 s timeout and fails with a third distinct message. The suite is no longer offline-safe or deterministic.

**Not affected.** The SSRF guard still runs ahead of the fetch — all 3 autofill/url tests pass, including private-host rejection.

**Root component.** `apps/api/src/adapters/legacy_backend/domain.py` (`product_url_autofill`).

---

## F-03 — `alembic upgrade head` migrates the wrong database
**Severity P1 · OPEN · onboarding**

**Reproduction.** Set `DATABASE_URL` only in `apps/api/.env`, then run `alembic upgrade head` from `apps/api/`.

**Evidence.** Migrations reported success, yet the app's database had **0 tables** while a stray `local-dev.db` had all 9 (`alembic_version, jobs, persona_preview_personas, persona_preview_runs, studies, study_assets, study_product_enrichments, study_section_states, user_usage_counters`). Exporting `DATABASE_URL` into the environment fixed it.

**Cause.** `apps/api/alembic/env.py:18` reads `os.getenv("DATABASE_URL")` and does **not** load the `.env` file; `AppSettings` (pydantic-settings) does. With nothing exported, alembic falls back to `alembic.ini`'s `sqlalchemy.url = sqlite:///./local-dev.db`.

**Masked in production** because `render.yaml` supplies a real environment variable.

**Credit:** the `database_schema` health check **added by `7645dfa`** detected this immediately with an actionable message. That check works as intended.

**Root component.** `apps/api/alembic/env.py` + README setup instructions.

---

## F-04 — A 100%-fabricated run reports `status: "completed"`
**Severity P0 · OPEN · blocks classroom use**

**Reproduction.** Run any mode while the OpenRouter account cannot fund the request.

**Evidence.** N=4, Q=3, all three modes:

| Mode | status | records | truly_live | fallback | provider_errors | **live_answer_rate** |
|---|---|---:|---:|---:|---:|---:|
| split | completed | 12 | 0 | 12 | 4 | **0.0** |
| mirror | completed | 24 | 0 | 24 | 8 | **0.0** |
| stability | completed | 36 | 0 | 36 | 12 | **0.0** |

**Which layer failed — diagnosed, not assumed.** The credential was valid: `GET /models` → 200 (414 models) and a direct `POST /chat/completions` with `max_tokens=50` → **200 with a real completion**. The app's calls returned:

```
HTTP 402  "This request requires more credits, or fewer max_tokens.
           You requested up to 1200 tokens, but can only afford 82."
GET /credits → total_credits 5.0, total_usage 5.19975 → balance −$0.1998
```

So the *failure* was **provider billing**. The **defect is the handling**:

1. **402 is not fail-fast.** `domain.py:471` fail-fasts only on `{401, 403}`. Billing exhaustion is hard and non-transient, yet degrades silently into invented data.
2. **The actionable provider message is discarded.** `_extract_provider_error_detail` is called **only** in the 401/403 branch. The 402 body contains an exact remedy and a link; the user-facing warning says only *"OpenRouter returned N provider-level error(s); temporary deterministic fallback filled the missing answers."*
3. **Fabricated rows carry no provenance.** `MockResponseRecord` has no `is_fallback` field, and the synthesized answer is stamped with the **real** provider model name (`domain.py:499`). Only open-text fallbacks are detectable, via a literal `"Mock response from …"` prefix.
4. **The diagnostics render nowhere.** `SimulationRunDebugSummary` is computed, persisted and **typed in the frontend** at `apps/web/src/lib/api.ts:254-263` — and no component reads it. Same for `run_conditions` and `persona_generation_mode`.

**Silent partial fallback is the common case even when billing is healthy.** `run_manager.py:447-450` requires an *exact* case-insensitive option match for `single_choice`; a model answering "Maybe" has its answer discarded and replaced by a seeded pick. An existing test codifies this (`test_legacy_live_simulation.py:230-237`). **The fabricated choice enters the distribution charts as if the model had said it.**

**Consequence.** A researcher or student sees a complete, green, plausible dataset that is entirely fiction.

**Root component.** `domain.execute_simulation_run` error handling + frontend run summary.

---

## F-04b — A retired model ID silently fabricates its entire share
**Severity P0 · OPEN · blocks classroom use · no regression test**

**Reproduction.** Mirror, N=3, Q=3, with credits available.

**TEST 1 — both models valid** (`openai/gpt-4o-mini`, `google/gemini-2.5-flash`):
```
status=completed  records=18  live_answer_rate=1.0
truly_live=18  fallback=0  provider_errors=0  malformed_json=0  warnings=0
[openai/gpt-4o-mini]      "Cost of installation and maintenance."
[google/gemini-2.5-flash] "The cost is a big factor for me right now, especially with other family expenses."
```
**The live pipeline is genuine and correct.** This is a PASS and must be reported as such.

**TEST 2 — substituting the retired `google/gemini-2.0-flash-001`:**
```
status=completed  records=18  live_answer_rate=0.5
truly_live=9  fallback=9  provider_errors=3
  openai/gpt-4o-mini            real=3  fabricated=0
  google/gemini-2.0-flash-001   real=0  fabricated=3
[google/gemini-2.0-flash-001] "Mock response from PERS_001: This feels practical for my home ..."
warnings: 2
```

**Consequence for research validity.** One model's entire share becomes deterministic filler stamped with its real name. The **Model Difference** chart then compares a live LLM against a seeded heuristic and reports "differences observed" — so "examining disagreement between LLMs" silently becomes LLM-vs-mock. Neither warning names the failing model or states that the ID does not exist.

**Match to Dr. Wang's 12 Aug session.** She reported *"completed with 2 warnings"*. This configuration produces **exactly 2 warnings** in exactly that shape. Her 20-persona × 2-model mirror run may well have been ~50% fabricated with no on-screen indication.

**Root component.** `domain.execute_simulation_run` (per-model error accounting) + missing model-validity check.

---

## F-05 — Three conflicting "responses" counts
**Severity P1 · FIXED+VERIFIED (`72d2368`) · verified live on a mirror run**

See `04_Experiment_Mode_Verification.md` §3 for the full table and causes.

- `total_generated_responses` is **always `sample_size`** (4 in all three N=4 modes) because `_call_with_supported_kwargs` silently drops the `records` kwarg.
- The UI tile counts distinct `respondent_id`, which Mirror deliberately reuses → **Mirror under-reported by a factor of M**.
- `test_legacy_live_simulation.py:146-148` currently asserts the incorrect value as expected.

**Consequence.** A 20×2×32 mirror run performs 40 executions and stores 1,280 records while the summary shows "20".

**Root component.** `domain._run_simulation_compat` / `_call_with_supported_kwargs`; `run-simulation-section.tsx:643-673`.

---

## F-06 — Insights does not generalize, and fabricates Strongest Segment
**Severity P0 · FIXED+VERIFIED (`15dffc9`, `b60242b`, `71bbf3b`) · all three defects closed**

**Reproduction.** Two identical coffee-subscription studies (N=6, 4 questions, same data semantics), differing **only** in question-ID naming.

**Variant A — non-colliding `C1..C4`:**
```
barrier_ranking      available=False  "Barrier matrix items were not found in this run."
interest_ladder      available=False  "Core decision-ladder questions were not found."
message_performance  available=False  "Positioning concept pairs were not found in this run."
segment_heatmap      available=False  "Not enough numeric question-by-segment data..."
use_case_share       available=False  "Primary use question Q3 was not found."   <-- leaks Neo schema
model_difference     available=True
top_findings: 1
strongest_segment = 'Balanced Mainstream'   weakest_segment = 'N/A'
```

**Variant B — colliding `Q1..Q4`:**
```
interest_ladder      available=True   segment_heatmap available=True   use_case_share available=True
top_findings: 3  ("Top intended use", "Decision ladder", "Model comparison")
top_use_case = {'label': '51', 'share': 16.7}      <-- a DOLLAR AMOUNT from the numeric price question
average_interest = 3.33
strongest_segment = 'Family Upgraders'  weakest_segment = 'Remote Professionals'
```

**Defect 1 — fabrication.** `domain.py:2733-2765`:
```python
segment_scores = _segment_score_table(df)     # keyed on Q0B/Q1/Q2 only
if not segment_scores:
    segments = _list_segments(df)
    return segments[0] if segments else "N/A" # alphabetically first
```
`'Balanced Mainstream'` is simply the alphabetically first of `['Balanced Mainstream','Family Upgraders','Remote Professionals','Wellness-Oriented']`. It is captioned *"Segment with the strongest overall directional signal in this run"* and injected into the evidence package as `exec_strongest_segment`, which the summarising LLM is instructed not to contradict. `weakest_segment='N/A'` is the incoherent tell.

**Defect 2 — silent mislabeling.** `schema_normalizer.py:49` auto-assigns `f"Q{index}"` to unlabeled questions, so a plain student-written survey **will** produce `Q1..Q4` and hit Variant B. This is the default outcome, not a contrived case.

**Defect 3 — schema leakage.** A coffee study is told *"Primary use question Q3 was not found."*

**What is correct:** no crash, no NaN, no divide-by-zero; `model_difference` is fully generic; five metrics degrade cleanly to `available: false`.

**All survey-ID hardcoding lives in one file** — `domain.py` (L2238, 2331, 2413, 2464, 2492, 2518, 2540-2543, 2573, 2759-2761). The legacy analysis package and the entire frontend contain none. The problem is contained and fixable.

**Root component.** `apps/api/src/adapters/legacy_backend/domain.py` insight builders.

### Status after the fixes — what "partial" means

| Defect | Status | Commit |
|---|---|---|
| 1 — Strongest Segment fabricated from alphabetical order | **CLOSED** — returns `None` when fewer than two segments can be scored | `15dffc9` |
| 3 — Neo schema vocabulary shown to custom studies | **CLOSED** — generic wording | `b60242b` |
| 2 — **silent mislabeling when ids collide** | **CLOSED** — Neo metrics gated to the Neo study mode | `71bbf3b` |

Neither fix touched *availability*. `b60242b` changes only the `message` string on an already-unavailable
chart; the builders still key on the literal ids `Q1`, `Q2`, `Q3`, `Q0B`, `S3`, `Q5_*`, `Q9A/Q9B`–`Q13A/Q13B`.
When a custom survey happens to use those ids, the metrics report `available: true` and label the data with
Neo's meanings.

**Re-verified 20 Aug on the composed branches** (`b60242b` + cherry-picked `15dffc9`, temp branch
`tmp/f06-compose`) with one coffee-subscription dataset run twice, differing only in question-ID naming.
`Q1` = "What would you pay per month?" (18/29/40/51 dollars), `Q2` = "How many bags per month?" (1–3),
`Q3` = "Preferred brew method?".

```
NON-COLLIDING  C1/C2/C3          COLLIDING  Q1/Q2/Q3
  use_case_share      False        use_case_share      True   Pour over 37.5% -> "Primary intended use"
  interest_ladder     False        interest_ladder     True   Q1 "Price-point interest" 100.0
                                                              Q2 "Purchase likelihood"  0.0
  segment_heatmap     False        segment_heatmap     True   rows Q1, Q2
  strongest_segment   None         strongest_segment   Wellness-Oriented
  average_interest    None         average_interest    34.5
```

`34.5` is the arithmetic mean of the four dollar prices. The UI renders it as
**"Average Interest · 34.5 · Directional score from the latest run"**
(`apps/web/src/components/sections/insights-section.tsx:286-295`).

**Why this is the residual P0.** After `15dffc9` the fabricated value is gone, so the incoherent
"Strongest: X / Weakest: N/A" tell that used to expose the problem is gone too. In the colliding case the
strongest segment is now genuinely *computed* — by scoring dollar amounts and bag counts as though they were
interest ratings. The output looks more trustworthy than before while being just as wrong. There is no
on-screen signal that distinguishes it from a correct Neo reading.

**Why F-14 does not close it.** `33ecf21` lets a researcher *choose* ids the Neo metrics will not claim
(`PRICE:`, `BREW:`), which is why the non-colliding column above is clean. It does not change the default:
`schema_normalizer.py:49` still assigns `f"Q{index}"` to any question that declares no id, so a plain
markdown survey — the common classroom case — still lands on `Q1..Qn` and still hits the colliding column.

**Now reproducible from the repository's own demo data.** `ff9e36f` ships a Cortado Roasters coffee
subscription preset. Bootstrapping it and running it on the combined tree (`f048fdd`, 4 respondents,
2 models, 128 live answers, no fabrication) produces:

| Coffee survey question | What it actually asks | What the Neo metric calls it |
|---|---|---|
| `Q1` Category interest | interest in a subscription, 1–5 | **"Price-point interest"** — 75.0 |
| `Q2` Current spend | monthly spend band in dollars | **"Purchase likelihood"** — 0.0 |
| `Q3` Where you buy today | current purchase channel | **"Primary intended use"** — Local coffee shop or roaster, 75% |

`average_interest` reports **3.75**, computed across category interest and a dollar spend band.
`strongest_segment` is correctly `None` — `15dffc9` holds — so the incoherent tell that used to expose
this is gone while the mislabeling remains.

This is no longer a contrived reproduction: it is the team's own demo preset, and a professor running
the coffee study sees "Purchase likelihood 0.0" for a question about what people currently spend.

**Closed 21 Aug in `71bbf3b`, verified live.** Reading an id is not evidence that a question means what
Neo's does; the study mode is. The six Neo metrics now run only for the Neo study — barrier ranking,
message performance, use-case share, interest ladder, segment heatmap, average interest, and
strongest/weakest segment. Nothing is substituted for a Custom Study, because there is no honest
stand-in for "how does this audience rank the Neo barrier matrix" in a survey that never asked it.

Same Cortado preset, same run shape (4 respondents, 2 models, 128 live answers, 0 fabricated):

| | Before (`8ba31ee`) | After (`71bbf3b`) |
|---|---|---|
| `barrier_ranking` | unavailable | unavailable |
| `message_performance` | **available** | unavailable — *"This insight is not applicable to this survey."* |
| `use_case_share` | **available** — Local coffee shop or roaster 75% as "Primary intended use" | unavailable |
| `interest_ladder` | **available** — Q1 "Price-point interest", Q2 "Purchase likelihood" 0.0 | unavailable |
| `segment_heatmap` | **available** — rows Q1, Q2 | unavailable |
| `model_difference` | available | **available** — unchanged |
| `average_interest` | **3.75** (a rating averaged with a dollar spend band) | `None` |
| `strongest_segment` | `None` | `None` |
| findings | Top intended use · Decision ladder · Model comparison | **Model comparison** only |

Neo re-verified in the same session and unchanged: all six charts available, ladder rows still
`S3` Feasibility · `Q0B` Category interest · `Q1` Price-point interest · `Q2` Purchase likelihood,
`average_interest` 3.5, and the four Neo findings intact.

One further leak was found and closed while testing: the realism scorecard told a Custom Study
*"Realism scorecard is shown only for Neo Smart mode."* — Neo product vocabulary in a study the reader is
not running. It now uses the same generic wording.

**Still deferred, and still the real answer.** Declarative semantic roles (`price_sensitivity`,
`purchase_intent`, `primary_use`) resolved from survey metadata would let a Custom Study *earn* these
metrics by declaring what its questions mean. The gate stops the false claims; it does not give custom
surveys their own version of them.

---

## F-07 — Neo interview fixture is undetectable by any client
**Severity P0 · OPEN · blocks Dr. Wang's 21–27 Aug step · no regression test**

**Evidence.**
- `interview_service.py:177` short-circuits `study_mode == "neo_smart"` to `ensure_demo_interview_run` **before** the OpenRouter key check. No interview call, no judge call.
- `demo_interview_fixtures.py`: `DEMO_MODEL_A="openai/gpt-4.1-mini"`, `DEMO_MODEL_B="google/gemini-2.5-flash"`, `DEMO_JUDGE_MODEL="demo/stamp-fixture"`.
- `PROTOTYPE_TRANSCRIPTS_PATH` = `apps/api/demo_data/prototype/interview_transcripts.csv` — **does not exist**, so every fixture takes the fully-generated branch.
- Answers are a hardcoded `if question_id == "IQ1": … elif "IQ2": …` chain of eight fixed sentences. **"Model B" is not a second model** — it appends a fixed clause to Model A's text. The "grounding report" is a **lookup table on `fit_tier`** (strong→1.0, soft→0.75, latent→0.5, edge→0.25). Themes are pre-written English with mention counts computed as `max(1, len(pairs)//2)`.
- **`_serialize_interview_job` returns only** `job_id, status, persona_count, model_a, model_b, grounding_report, pairs, error, queued_at, completed_at` — it **omits `judge_model`, `demo_fixture`, and `fixture_source`**. The backend *does* send `generated_from_demo_fixture` for insights, and the frontend TypeScript type discards it.
- **Provider quota is still charged** for the fixture (`interview_service.py:166-173` runs above the Neo branch).

**Consequence.** The API advertises two real-sounding model IDs for text no model produced, and exposes **no field** by which a client could detect a fixture. The UI states the opposite: *"Both AI models interview every persona independently. A judge LLM then scores agreement across four dimensions — STAMP-style…"*, and elsewhere claims a score *"analogous to Krippendorff's α"* for what is a mean of binary LLM judgments with no chance correction.

**Custom Study interviews are genuinely live.** The asymmetry is that the guided demo path — the one a first-time viewer and a student sees — is the fabricated one.

**Root component.** `apps/api/src/services/interview_service.py`, `demo_interview_fixtures.py`, `apps/web/src/lib/api.ts`.

---

## F-08 — PDF support is inverted; plain markdown collapses to open text
**Severity P1 · PARTIALLY FIXED (`e9c51f4`) · the blocker is closed; two sub-defects remain open**

| Input | Result |
|---|---|
| MD — Neo preset | **PASS** — 32 questions, `{single_choice: 8, likert: 24}`, matrix `Q5 → Q5_1..Q5_7`, 26 transparent warnings |
| DOCX — aytm Neo (252 KB) | **PASS** — 39 questions, `{single_choice: 9, likert: 26, open_text: 2, multi_choice: 2}` |
| **PDF — real Neo survey, Google Forms export** | **FAIL — HTTP 400** `Duplicate question ids found: Q1` |
| **PDF — aytm joint challenge** | **FAIL — HTTP 400** `Duplicate question ids found: Q1, Q2, Q3, Q6` |
| **PDF — a marketing brochure, not a survey** | **"PASS" — HTTP 200**, accepted as a valid 3-question open_text survey |

`.pdf` is an advertised format with `pypdf` as a hard dependency and a health check, and has **zero test coverage**. A student exporting a Google Form to PDF — the most likely classroom path — cannot upload it.

**Markdown format sensitivity (fair-test result).** The parser *does* generalize to non-Neo content, but only with Neo's authoring conventions:
```
plain markdown (student-style)      Neo-style markdown
  Q1  open_text  opts=0               C1  single_choice  opts=3
  Q2  open_text  opts=0               C2  likert  opts=5 min=1 max=5
  Q3  open_text  opts=0               C3  open_text   <-- "how much per month in USD" NOT numeric
  Q4  open_text  opts=0               C4  open_text
```
Requires `**ID. Title** text`, `- [ ]` checkbox options, and a markdown table for Likert scales. Plain `1.` numbering with `- Yes` bullets yields **all open_text**, warning only *"Inferred open_text … because type was missing"* — never *"options were present but not recognised"*. **Numeric is never inferred.** Open text can never exceed "Low confidence" in `assess_question_trust`, and no choice/Likert/numeric charts are produced.

**This is the entry point to F-06:** plain markdown is auto-numbered `Q1..Q4`.

### Status after `e9c51f4` — blocker closed, two sub-defects open

| Sub-defect | Status |
|---|---|
| Google Forms PDF rejected with `Duplicate question ids found: Q1` | **CLOSED** |
| Google Forms PDF parses as all `open_text` — no options, so no charts | **OPEN** |
| A brochure with no questions is accepted as a survey | **OPEN** |
| Plain markdown (`1.` + `- Yes`) collapses to `open_text`; numeric never inferred | **OPEN** |

**Root cause of the blocker.** The parser mapped any bare list number `N.` to `QN`. A Google Forms
export numbers every field including the email capture, so `1. Email*` became `Q1` while the survey's own
`Q1.` was also `Q1`. A number in a list is a position, not a name; the parser now returns an id only when
the document named one, and the normalizer assigns the rest while skipping ids the document claims.

**A regression this exposed.** The `.docx` fallback was reached only when the primary parser happened to
raise on duplicate ids — an accident that correlated with the primary parser having done badly, not a
check that it had. With the collision gone the primary parser "succeeded" on the AYTM docx and returned
**32 questions, all open text**, against the fallback's **39 with a real type mix**, and nothing would
have reported the downgrade. The fallback is now chosen on the result rather than on an incidental error.

**Upload matrix, re-measured on `e9c51f4`:**

```
PDF  Google Forms Neo survey    400 -> OK, 43 questions (all open_text)
DOCX aytm Neo survey            OK,  39 questions {single_choice 9, likert 26, open_text 2, multi_choice 2}
PDF  aytm joint challenge       still rejected - it is a design brief, not a survey
PDF  Neo background brochure    still accepted as a 5-question open_text survey   <-- open
```

**Why option recovery was not attempted.** In the Google Forms export, `pypdf` returns a question's
options separated from the question by page headers and footers:

```
'Q1. Purchase interest at $23,000'
'Based on the product description above, how interested would you be in'
...
'3/12/26, 11:43 AM Neo Smart Living — Tahoe Mini Survey'
'https://docs.google.com/forms/d/16_X6.../edit 5/25'
'7.'
'Mark only one oval.'
```

Reassembling options across that is a parsing project, not a small change, and was deliberately left
rather than half-built. Until it is done, a PDF upload produces a survey with no scorable questions:
no distributions, no means, no charts, and nothing above "Low confidence" in the trust assessment.

**Root component.** `legacy_runtime/backend/survey/parser.py`, `schema_normalizer.py`, `adapters/legacy_backend/survey_docx_fallback.py`.

---

## F-09 — Fallback model catalog contains a retired model
**Severity P1 · FIXED UPSTREAM in `b3bd4b5` · verified on the combined tree `f048fdd`**

> **Closed 20 Aug.** `google/gemini-2.0-flash-001` was replaced with `anthropic/claude-sonnet-4.5` in the
> fallback catalog, so the degraded menu no longer offers a model the provider will reject. Confirmed
> against the live provider: selecting the retired id now returns 503 with *"No endpoints found for
> google/gemini-2.0-flash-001"* rather than a fabricated half-run (scenario C below). The original
> finding is kept below unchanged.

`domain.py:150-163` hardcodes a **two-entry** fallback catalog served when the live `/models` fetch fails:
`openai/gpt-4o-mini` and **`google/gemini-2.0-flash-001`**.

Verified against the live catalog (414 models): `google/gemini-2.0-flash-001` is **absent**; so is `google/gemini-2.0-flash`; `google/gemini-2.5-flash` is present.

**Consequence.** In the degraded state a user is offered a 2-item menu, half of which is dead — and selecting it triggers F-04b (100% fabricated rows for that model, stamped with its real name).

**Scope note.** The Neo bootstrap defaults (`openai/gpt-4o-mini`, `anthropic/claude-sonnet-4.5`) are **both valid**, so the guided demo path is not affected by default.

**Root component.** `apps/api/src/adapters/legacy_backend/domain.py::list_model_catalog`.

---

## F-10 — No LICENSE file
**Severity P1 · OPEN · blocks the CARLE deposit**

No `LICENSE` or `COPYING` file is tracked anywhere in the repository. Compounded by F-01: part of the runtime lives in a third-party repository under a different owner. Directly answers Dr. Wang's kickoff question 1.

---

## F-11 — Concurrent first-request-of-day returns HTTP 500 (usage-counter race)
**Severity P0 · OPEN · found during browser E2E · blocks classroom use · no regression test**

**Discovered by** clicking "Start Setup" twice on the landing page. The browser console showed a 500 and the
page rendered blank with the nav stranded at the bottom.

**Failing request.** `POST /api/backend/api/v1/studies` → **500 Internal Server Error**
(the immediately preceding identical request returned 200).

**Exception.**
```
sqlite3.IntegrityError: UNIQUE constraint failed:
  user_usage_counters.owner_user_id, user_usage_counters.metric_key, user_usage_counters.bucket_date_utc
```

**Root cause — check-then-act with no upsert.** `apps/api/src/services/usage_limits.py::consume_daily_quota`:
```python
row = session.scalar(select(UserUsageCounter).where(...owner..., ...metric..., ...bucket...))
current_count = row.count if row else 0
...
if row is None:
    row = UserUsageCounter(owner_user_id=..., metric_key=..., bucket_date_utc=bucket, count=1)
else:
    row.count += 1
session.add(row)
```
Two concurrent requests both read "no row", both INSERT, and the second violates the unique constraint.
There is no `ON CONFLICT` / upsert and no `IntegrityError` retry.

**Deterministic reproduction.**
```
# clear the counter row to simulate the first request of a UTC day, then fire two concurrent creates
sqlite3 qa.db "DELETE FROM user_usage_counters;"
curl -X POST .../api/v1/studies & curl -X POST .../api/v1/studies & wait

attempt 1: A=500 B=200
attempt 2: B=200 A=500
attempt 3: B=200 A=500
attempt 4: A=200 B=500      -> 4/4 reproduce
```
With the counter row already present, concurrent requests all return 200 — confirming the window is the
**INSERT of the first counter row for a (user, metric, UTC date) triple**.

**Consequence for classroom use.** This fires on the application's primary entry action. It is reachable by
an ordinary double-click on "Start Setup", and by React's development double-effect. Because the bucket is
keyed on the **UTC date**, every student's first action of the day sits in this window — and it applies to
**every quota-metered action**: study creation, survey/image upload, simulation runs, stability checks and
interview runs. The user sees an unexplained 500 and a blank page with no recovery guidance.

**Root component.** `apps/api/src/services/usage_limits.py::consume_daily_quota`.

---

## F-12 — Mode-card selected state fails non-text contrast, and is not exposed programmatically
**Severity P1 (accessibility) · OPEN · confirmed in browser · resolves Dr. Wang item 3 · no regression test**

**Reproduction.** Load the app in **dark** scheme, scroll to Study Setup, select "Neo Smart Living Demo",
then compare the two mode cards.

**Measured from live composited colours** (not from a screenshot):
```
ground                                rgb(10, 15, 19)
selected   border rgba(118,228,255,0.30) -> rgb(42, 79, 90)
unselected border rgba(118,228,255,0.14) -> rgb(25, 45, 52)

contrast selected vs unselected border : 1.61 : 1
contrast selected border vs ground     : 2.17 : 1
WCAG 1.4.11 threshold (non-text)       : 3.00 : 1
```

The only card-level difference is a **1 px border differing solely in alpha**. Neither card has a background
fill, box-shadow or outline to distinguish it. Additionally **neither card sets `aria-pressed` or
`aria-current`**, so the selected state is not conveyed to assistive technology at all.

**Mitigation present:** the selected card's badge changes from `GUIDED DEMO` to **`CURRENT SELECTION`**,
which does communicate state to a sighted user who reads it.

**Consequence.** Dr. Wang's item 3 reproduces objectively. In a classroom this is the first interaction a
student makes, and the affordance that indicates "you have chosen this path" is effectively invisible.

**Root component.** `apps/web/src/components/sections/study-mode-section.tsx` (card styling ~L226-311).

---

## F-13 — Likert charts render an empty named scale beside unlabelled numeric buckets
**Severity P1 · OPEN · confirmed in browser · affects 24 of 24 Likert questions · no regression test**

**Reproduction.** Neo study, Mirror N=3, Q=32. Open Result → any Likert question.

**Evidence — Q1 ("How interested are you…", declared 1–5 with named scale points):**
```
raw records            : [4, 4, 4, 3, 4, 4]        (independent mean 3.8333)
UI response_count      : 6
UI distribution:
   Not at all interested     count=0   pct=0.0
   Slightly interested       count=0   pct=0.0
   Moderately interested     count=0   pct=0.0
   Very interested           count=0   pct=0.0
   Extremely interested      count=0   pct=0.0
   3                         count=1   pct=16.7
   4                         count=5   pct=83.3
SUM of UI counts = 6 = response_count
```

**Scope: 24 of 24 Likert cards** are affected. `Q0B/Q1/Q2` show 5 named labels at zero plus 2–3 numeric
buckets; the `Q5_*` barrier matrix shows 0 named labels and 5 numeric buckets.

**Data is NOT lost** — every count reconciles with the raw records, and no chart sums to zero. This is a
**presentation defect, not a data-correctness defect**: the model answers Likert questions numerically, and
the chart appends the numbers as new categories instead of mapping `3 → "Moderately interested"`,
`4 → "Very interested"`.

**Consequence.** A student reading the headline interest question sees every named option at **0%** plus two
unexplained bars labelled "3" and "4". The declared scale is meaningless on screen, and the chart invites the
conclusion that nobody chose any of the offered answers. It affects **24 of the 32 questions** in the Neo
survey, including the interest and barrier measures the study exists to read.

**Root component.** Likert distribution assembly in `apps/api/src/adapters/legacy_backend/domain.py`
(`_build_analysis_dashboard_questions`) — scale-point mapping for numeric Likert answers.

---

## F-14 — Survey parser rejects non-numeric question IDs, forcing every custom study into the Neo collision
**Severity P0 · OPEN · confirmed · blocks the teaching-module goal · no regression test**

**Reproduction.** Upload a Neo-style markdown survey whose IDs are words — `BENEFIT`, `INTEREST`, `PRICE`,
`FEATURES`, `CONCERN` — with content identical to a `Q1…Q5` version that parses fine.

```
HTTP 400 validation_error
"No recognizable questions were found in the Markdown file. Expected lines like `Q1:` and `Type:`."
parsed questions: 0
```

**Root cause.** `legacy_runtime/backend/survey/parser.py:12` — the sole question-ID pattern:
```python
re.compile(r"^\s*(?P<id>[A-Za-z]?\d+[A-Za-z]?)\s*[:\.\-]\s*(?P<text>.+)$", re.IGNORECASE)
```
An ID must be *optional letter → digits → optional letter*. `Q1`, `S3`, `Q0B`, `Q9A` match. Any purely
alphabetic ID **can never match**.

**Consequence — this is the finding that makes F-06 unavoidable.** The parser *forces* `Q<number>` naming;
the Insights layer then *interprets* `Q1/Q2/Q3` as Neo's price-point interest, purchase likelihood and
primary intended use. A custom study cannot opt out by choosing meaningful IDs, because meaningful IDs are
rejected at upload. **Every custom study is therefore guaranteed to hit the Neo semantic collision.**

Demonstrated live: a study-planning app for students reported **"Top intended use = `$12`"** (sourced from
the price question) and an **interest ladder that does not exist in the survey**.

**Root component.** `legacy_runtime/backend/survey/parser.py` (ID regex) + `domain.py` insight builders.

---

## F-15 — Strongest and weakest segment can be reported as the same segment
**Severity P1 · OPEN · confirmed · no regression test**

**Reproduction.** Custom study `std_314dc19552a5` (StudyFlow/FocusPlan), N=3, Mirror, segments present
`['Balanced Mainstream', 'Remote Professionals']`.

```
segment_story: strongest='Balanced Mainstream'  weakest='Balanced Mainstream'
```

The **same segment is presented simultaneously as the strongest and the weakest**. This is a distinct
consequence of the F-06 fallback path (alphabetical selection when the Neo scoring IDs are absent), but it
is materially different in effect: rather than a silently wrong single value, the UI now shows two
contradictory claims side by side and labels both as evidence.

Earlier API-level runs produced `strongest='Balanced Mainstream' / weakest='N/A'`; with two segments present
the degenerate case collapses both to the same label.

**Root component.** `domain.py::_compute_strongest_segment` / `_compute_weakest_segment`.

---

## Upstream commit review — `2691642` (Yaza Myo Tun, 2026-08-20)

**Scope:** one commit on `yaza_Aug_work`, 15 files, +339 / −54. Frontend-heavy plus two backend changes.
**No tests were added.** Backend suite at that tip: **64 passed, 1 failed** — the same F-02 test failing for
the same reason. No regressions, no new coverage.

### Findings this commit CLOSES
- **F-12 / item 3 — fixed.** Selected mode card now has a solid 2px `--color-brand-primary` (#76e4ff) ring
  plus inner ring and glow, and sets **`aria-pressed`**. Re-measured **1.61:1 → 9.76:1** vs unselected
  (13.12:1 vs ground). Both halves of the recommendation implemented.
- **Item 6 — fixed.** `TokenInput` chips are no longer click-to-remove; removal moved to a dedicated `×`
  with `aria-label`, and an additive "Suggestions — click to add" row was introduced.
- **Items 10, 11 — fixed.** Notes relabelled in all three sections; Industry became a 16-option select that
  preserves pre-existing custom values.
- **Item 13 — improved.** The run status message now previews up to two warnings and names the
  "Run warnings" panel. The numeric diagnostics remain invisible, so **F-04's visibility gap stays open**.

### Findings this commit does NOT touch — all still open
`F-01, F-02, F-03, F-04, F-04b, F-05, F-06, F-07, F-08, F-09, F-13, F-14, F-15`.

Verified directly rather than inferred:
- `_compute_strongest_segment` is byte-identical — the alphabetical fabrication (F-06) is unchanged.
- `google/gemini-2.0-flash-001` is still hardcoded in the fallback model catalog (F-09).
- `parser.py`, `interview_service.py`, `usage_limits.py`, `alembic/env.py` and
  `tests/test_studies_endpoints.py` are all untouched.
- No change to the Likert distribution assembly (F-13).

### F-11 — client-side mitigation only, root cause untouched
`apps/web/src/providers/study-provider.tsx` adds a `bootstrapStartedRef` guard whose own comment reads:
*"React Strict Mode may run this effect a second time … so a transient 500 cannot leave the hero permanently
stuck on 'Preparing Setup…'."*

He encountered the F-11 symptom and suppressed **one trigger** — React's development double-effect. He did
**not** change `consume_daily_quota`, so the check-then-act race is intact and still fires for genuine
concurrency: two browser tabs, a real double-click, or several students starting at the same time on a fresh
UTC day, across every quota-metered action.

**Conclusion: his client guard and the server fix on `fix/f-11-quota-race` (`84b30ed`) are complementary.
The client guard alone is not sufficient.** F-11 remains OPEN on `yaza_Aug_work`.

---

## F-16 — "Reset Product Details" now makes a claim that is untrue after a reload
**Severity P1 · OPEN · introduced in `2691642`**

`2691642` adds an `isProductReset` flag so the product re-seed effect yields `EMPTY_PRODUCT_DRAFT` rather than
re-seeding Neo defaults. Within a single session this is a real improvement over the previously recorded
behaviour (item 8).

However `isProductReset` is `useState(false)` — **not persisted to storage or the server** — and
`handleClearSavedContext` still makes **no API call**, so the saved product section is untouched. On reload
the flag is `false`, `resolveSetupSeedSource` returns `"saved"`, and the saved Neo product loads again.

The message was nevertheless changed to:
> "Product details were cleared. Add your own details, then save when ready. **Neo content will not return
> unless you load the demo examples.**"

That final clause is false after a page refresh. The prior wording — *"reset **locally** … replace what is
currently **saved**"* — was accurate. **The behaviour improved while the copy became misleading**, which for
a teaching tool is the worse half of the trade.

**Fix options:** clear the persisted section through the API on reset, or restore honest wording.
**Root component.** `apps/web/src/components/sections/product-section.tsx`.

---

## F-17 — Insights explains an all-fabricated run with the wrong reason
**Severity P1 · FIXED+VERIFIED (`627660e`) · verified live against a stub provider**

**Reproduction.** Scenario B below: a Neo run in which every answer failed coercion, so all 128 saved
records are fabricated and none are live.

```
GET /studies/{id}/analysis
  available       : False
  message         : "Every answer in this run was deterministic filler rather than a model response,
                     so there is nothing to analyse. Check the run diagnostics before relying on it."
  answer_sourcing : live 0, excluded 128, rate 0.0

GET /studies/{id}/insights
  available       : False
  message         : "The latest run does not include response records yet."   <-- untrue
  answer_sourcing : null                                                      <-- omitted
```

The run has 128 response records. Analysis says so accurately and reports the sourcing; Insights
reports a different, incorrect reason and drops the sourcing summary entirely. A reader on the Insights
page is told to wait for data that already exists, instead of being told the run was unusable.

**Why it matters.** The two surfaces disagree about the same run, and the one that disagrees is the one
that omits the evidence a reader would use to check. This is the failure mode F-04 exists to prevent,
reappearing one screen over.

**Root component.** `apps/api/src/adapters/legacy_backend/domain.py` — `build_insights_view` checks for
records before the live/fallback split, so an all-fallback run reads as an empty one.

---

## R-01 — Undocumented third-party runtime dependency (ZIP lookup)
**Severity P2 · OPEN · introduced in `2691642`**

`audience-section.tsx` now calls `https://api.zippopotam.us/us/{zip}` **from the browser** whenever the ZIP
field matches `^\d{5}$`, to autofill city/state. It is unauthenticated, has no timeout beyond an
`AbortController`, is absent from `.env.example`, `render.yaml` and all deployment docs, and is not on any
allowlist. Failures are swallowed by design (`catch {}`), so on a restricted classroom network the feature
silently stops working with no user-facing explanation. Researcher-entered ZIPs are sent to a third party.

**Action:** document it, decide whether it is acceptable for classroom networks, and surface a message when
the lookup fails rather than failing silently.

---

## R-02 — Product image analysis has no provenance
**Severity P2 · OPEN · introduced in `2691642`**

`domain.product_image_analysis` now falls back to `_openrouter_product_image_analysis` (a `gpt-4o-mini`
multimodal call) when Google Vision credentials are absent or Vision errors. The fallback is **honest about
failure** — it raises `ProviderUnavailableApiError` rather than fabricating, which is better than the survey
path (F-04). But the returned payload is **shape-identical** whichever engine produced it, and the UI copy
was generalised from "Google Vision" to "AI", so a researcher cannot tell which system generated the labels,
objects, colours or OCR text. Same class of gap as F-04 and F-07.

**Action:** return and display an analysis-source field.

---

## R-03 — `lg:overflow-hidden` on scrollable sections may clip overlays
**Severity P2 · OPEN · introduced in `2691642`**

`lg:isolate lg:overflow-hidden` was added to the Run and Result `SectionWrapper`s as defensive hardening for
item 14. Both sections are `scrollable`; clipping at ≥lg can cut off dropdowns, tooltips, popovers or sticky
elements that intentionally overflow. Not observed — flagged for a visual pass.

---

## Browser closure — Neo Insights & Interview (2026-08-17)

**Neo Insights — deterministic layer PASSES.** `top_use_case` 66.7% and `average_interest` 3.83 match
independent recomputation exactly; `strongest`/`weakest` are genuinely computed because the Neo IDs exist.
**F-06 is a generalization defect, not a Neo defect** — worth stating plainly to the professors.

**New evidence for F-04/F-05 visibility (no new defect ID):** in the Insights UI, `transparency_note`,
heuristic/exploratory wording, `live_answer_rate` and `persona_generation_mode` are **all absent**. The
default view opens with *"3 RESPONDENTS · 32 QUESTIONS"* and a *"reliability confidence read"* with no
caveat. The LLM's own `result_reliability` says *"With only 3 respondents…"* for a run of **6 executions /
192 answers** — **F-05's wrong count propagates into the model's stated reliability judgement.**

**F-07 — now proven end to end, not inferred.** Backend `result_json` for job `job_b450320f79c9` contains
`demo_fixture: True`, `fixture_source: 'generated_fallback'`, `judge_model: 'demo/stamp-fixture'`.
**All three are stripped by `_serialize_interview_job`** before the client sees the payload. Zero provider
calls occurred. The UI simultaneously asserts *"Both AI models interview every persona independently. A judge
LLM then scores agreement…"* and displays **STAMP GROUNDING SCORE 100% · PASSES THRESHOLD** with all four
dimensions at 100%. A word-scan of all three interview screens for `fixture / demo / seeded / pre-generated /
not live` returned **zero matches**. Severity confirmed **P0 (research transparency)**.

---

## Confirmed in browser (added after 02/03)

- **F-11** — usage-counter race → HTTP 500 on the primary entry action (**P0**, new).
- **F-12** — mode-card selected-state contrast 1.61:1 and no `aria-pressed` (**P1**, resolves item 3).
- **F-13** — Likert charts show an empty named scale beside unlabelled numeric buckets (**P1**, 24/24 cards).
- Item **14** (Result drawing over Run) — **PASS, does not reproduce.** With a completed run, sections tile
  exactly (`run-simulation` 18825–22426, `analysis` 22426–39763, `insights` 39763–43854), all `position:
  relative`, `z-index: auto`, DOM order correct, and **0** absolutely/fixed-positioned descendants escaping
  their section. Caveat: the transient Run→Result transition Dr. Wang described was not reproduced and may be
  timing- or viewport-dependent.
- **F-05 reproduced on screen:** the Run panel displays `RESPONSES 3` while the Result dashboard shows
  `6 RESPONSES` per question across `192` records — same run, contradictory numbers.
- **Preview vs Run grounding divergence proven at runtime:** Preview reports `heuristic_fallback` *and warns*;
  the Run reports `heuristic_only` and emits **no grounding warning**.
- **Live path is not clean even with two valid models:** `live_answer_rate 0.984`, 3 fabricated answers with
  **0 provider errors and 0 malformed JSON** — the silent coercion path of F-04. The fabricated records could
  not be identified even with full DB access and the schema.
- **Landing-copy transparency:** the hero advertises *"Realistic — GROUNDED PERSONAS"* while persona
  generation runs `heuristic_only` with no priors installed and **no run-time warning** (baseline §6).

### Harness note for anyone repeating this
The browser pane runs backgrounded (`document.visibilityState === "hidden"`), so Framer Motion
`RevealOnScroll` wrappers never fire and screenshots render blank with a mis-composited sticky nav.
**This is a harness artifact and is not a defect.** Verified by reading `innerText` (807 chars of correct
content) from a section that appeared visually empty. All browser findings above were therefore established
from DOM, computed styles, geometry, network traffic and API responses.
