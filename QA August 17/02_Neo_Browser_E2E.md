# 02 — Neo Smart Living: Browser E2E

## Session context

| Item | Value |
|---|---|
| Branch / SHA | `yaza_Aug_work` @ `7645dfa25412166fb4d6bd6e3f881e5ef926dc69` |
| Frontend | `http://127.0.0.1:3010` (Next.js 14.2.35 dev, local build of the target SHA) |
| Backend | `http://127.0.0.1:8010` (uvicorn, Python 3.11.15) |
| Database | isolated QA SQLite (`qa.db`), migrated to head |
| Auth | ungated dev mode (no Clerk, no access password) — **no credentials stored in this folder** |
| Viewport | 1280 × 720 |
| Colour scheme | **dark** |
| Browser | Chromium (in-app pane) |
| Date | 2026-08-17, 18:09 PDT |
| Backend health at start | `degraded` — `google_vision`, `grounding_priors`, `hud_lookups` warn; all hard checks `ok` |

### Harness limitation — read before interpreting anything here

The browser pane runs **backgrounded** (`document.visibilityState === "hidden"`). Two consequences:

1. The app's Framer Motion `RevealOnScroll` wrappers use viewport-intersection triggers, which **never fire** while the document is hidden. Sections therefore stay at `opacity: 0` and screenshots render blank, with the sticky nav mis-composited.
2. **This is a harness artifact, not an application defect, and is not reported as a bug.** Verified directly: with sections visually blank, `document.getElementById('study-mode').innerText` returned 807 characters of correct content.

**Consequence for method:** pixel screenshots from this pane are not trustworthy. All verification below is therefore done against the **DOM, computed styles, geometry, network traffic and API responses**, which are unaffected by the visibility state — and which are stronger evidence than a screenshot for everything except pure aesthetics. Where a visual judgement was required (item 3), it was resolved by **computing WCAG contrast ratios from live composited colours** rather than by eye.

A CSS override (`opacity:1 !important` on reveal wrappers) was injected **into the browser only** to attempt screenshot capture. No application source was modified.

---

## Stage 1 — Study Setup

| Check | Expected | Actual | Verdict |
|---|---|---|---|
| Duplicate workflow button removed (item 1) | Only "Start Setup" on the hero | DOM exposes `Start Setup` and `Start New Study`; **no "See Workflow" button** | **PASS** |
| Nav item count | 10 primary tabs | `Set Up, Audience, Product, Market, Survey, Experiment, Run, Result, Insights, Interview` | **PASS** |
| Step numbering (item 2) | Header shows "01" for Study Setup | Section header renders **`01. STUDY SETUP`** as a single merged chip | **PASS** |
| Contradictory "Step 1 of 6" chip | Absent | Not present in the DOM (present on `main`, deleted in `7645dfa`) | **PASS** |
| Mode cards present | Two selectable cards | `GUIDED DEMO / Neo Smart Living Demo` and `CUSTOM STUDY / General Custom Study` | **PASS** |
| Continue gating | Disabled until a mode is chosen | `Continue to Audience Setup` — `disabled: true` before selection | **PASS** |
| Selection feedback (text) | Obvious which card is selected | Selected card's badge changes from `GUIDED DEMO` to **`CURRENT SELECTION`** (gold tint) | **PASS** |

### Item 3 — dark-mode selected state: **FAIL (reproduced, quantified)**

Measured from live composited colours on the settled DOM, dark scheme:

```
ground (painted)                     rgb(10, 15, 19)
selected card border    rgba(118,228,255,0.30) → composited rgb(42, 79, 90)
unselected card border  rgba(118,228,255,0.14) → composited rgb(25, 45, 52)

contrast  selected vs unselected border : 1.61 : 1
contrast  selected border vs ground     : 2.17 : 1
WCAG 1.4.11 non-text contrast threshold : 3.00 : 1
```

The card-level distinction is a **1 px border differing only in alpha** (0.30 vs 0.14). At **1.61:1** it is well below the 3:1 threshold for non-text UI state indication, and the selected border is only 2.17:1 against its own ground. Neither card carries a background fill, box-shadow, or outline to differentiate it.

**Mitigation:** the textual `CURRENT SELECTION` badge does communicate state to a sighted user who reads it.
**Aggravation:** neither card exposes `aria-pressed` or `aria-current`, so the selected state is **not conveyed programmatically at all** — assistive technology receives nothing from the card itself.

**Verdict: Dr. Wang's item 3 is confirmed as a genuine accessibility defect**, now with objective measurements rather than an impression. Recommended: add a filled/elevated selected surface meeting ≥3:1 against the unselected state, and `aria-pressed` on both cards.

---

## Stage 1b — Defect found during entry: F-11

Clicking **Start Setup** produced `POST /api/backend/api/v1/studies` → **HTTP 500**, a blank page, and a console error. Root-caused to a check-then-act race in `consume_daily_quota` inserting the first `user_usage_counters` row of the UTC day; **reproduced deterministically 4/4**. Full detail in `05_Bugs_and_Blockers.md` → **F-11 (P0)**.

This is a browser-discovered defect that the API-level pass had not surfaced, because it requires two concurrent requests against a fresh daily counter.

Backend log excerpt (the raw dev-server log itself is transient and is not committed — it recorded
absolute paths into a scratch worktree that no longer exists):
```
sqlite3.IntegrityError: UNIQUE constraint failed:
  user_usage_counters.owner_user_id, user_usage_counters.metric_key, user_usage_counters.bucket_date_utc
```

---

## Stages 2–11 — NOT YET EXECUTED

The following stages of the Neo journey were **not** completed in this session and must not be read as passing:

| Stage | Status |
|---|---|
| Audience | **NOT RUN** — income wording, City/Area, ZIP, tag add/remove, save, refresh persistence, min/max validation |
| Product | **NOT RUN** — Neo prefill, Reset behaviour (local vs persisted), Notes clarity, Industry, URL autofill × 3 cases with API-source inspection |
| Market | **NOT RUN** — substitutes/features/objections/competitors, backwards-click concern (item 6) |
| Survey | **NOT RUN** in browser — *(parsed at API level: Neo preset = 32 questions, `{single_choice: 8, likert: 24}`)* |
| Experiment | **NOT RUN** — save-state clarity, saved-vs-unsaved badge contradiction, which config Run actually uses |
| Persona Preview | **NOT RUN** — grounding mode reporting vs Run behaviour |
| Run | **NOT RUN** in browser — *(verified at API level: valid model pair → `live_answer_rate = 1.0`, 18/18 live, 0 warnings)* |
| Result | **NOT RUN** — **item 14 overlap still unresolved**, chart cross-checks, filters, response-count semantics |
| Insights | **NOT RUN** in browser — *(verified at API level: see F-06)* |
| Interview | **NOT RUN** in browser — *(verified at source level: see F-07)* |

**Item 14 (Result drawing over Run) therefore remains `NEEDS VISUAL CHECK`.** It requires a completed run plus reliable geometry measurement; the plan is to compare the bounding boxes of the run panel and the analysis panel for intersection, rather than rely on screenshots from a backgrounded pane.

---

## Workflow summary (partial)

- **Set Up:** **PASS** on items 1 and 2; **FAIL** on item 3 (contrast, quantified); **P0 defect F-11** found on entry.
- **Audience:** not run
- **Product:** not run
- **Market:** not run
- **Survey:** API-verified only
- **Experiment:** not run
- **Persona Preview:** not run
- **Run:** API-verified only
- **Result:** not run — item 14 open
- **Insights:** API-verified only
- **Interview:** source-verified only

### Visual issues
- Item 3 — selected/unselected card state at **1.61:1**, below the 3:1 threshold (P1, accessibility).
- No `aria-pressed`/`aria-current` on mode cards (P1, accessibility).

### Functional issues
- **F-11** — concurrent first-of-day request returns 500 on the primary entry action (**P0**).

### Data-correctness issues
- None newly found in this stage. Previously confirmed: F-04, F-04b, F-05, F-06.

### Research-transparency issues
- The hero advertises **"Realistic — GROUNDED PERSONAS"** while persona generation runs on `heuristic_only` with no grounding priors installed and **no run-time warning** (baseline §6). Recorded as a transparency concern for the landing copy.

### Provider / environment issues
- Backend health `degraded`: `google_vision`, `grounding_priors`, `hud_lookups` all warn. Expected for a local QA environment; `grounding_priors` is substantive (baseline §6).
- Port 8000 was occupied by an unrelated local service; QA used 8010/3010.

### Priority roll-up for this stage
- **P0:** F-11
- **P1:** item 3 contrast; missing `aria-pressed`; grounded-personas landing claim
- **P2:** none recorded yet

---

# Session 2 — resumed run (same servers, same SHA)

Study `std_9c1596802cd7` · run job `job_5a0c348b41cf` · N=3 · M=2 · Mirror · R=1 · Q=32.
Models: `openai/gpt-4o-mini`, `google/gemini-2.5-flash` (both verified present in the live catalogue).

## Stages 2–6 — setup sections (bootstrap verification)

Selecting Neo mode saved **all five sections immediately** (`status: saved`, same timestamp).

| Section | Result | Verdict |
|---|---|---|
| Audience | saved on bootstrap | **PASS** (bootstrap) |
| Product | **fully populated** — business, industry, product name/type/description, target customer, `$23,000 delivered and installed`, 8 key features, 6 use cases | **PASS** |
| Market | saved on bootstrap | **PASS** (bootstrap) |
| Survey | `Neo Smart Living — Tahoe Mini Survey (High-Priority Version)`, **32 questions**, `{single_choice: 8, likert: 24}`, ids `S3, Q0B, Q1, Q2, Q3, Q5_1…`, **26 parse warnings** | **PASS** — UI count matches parsed schema exactly |
| Experiment | bootstrap default **N=100, split, `gpt-4o-mini` + `claude-sonnet-4.5`** (both valid) | **PASS**, see cost note |

**Dr. Wang Test Log row 3 — "the Product page arrived empty" does NOT reproduce.** Product is fully
prefilled by the bootstrap. Her session may predate a fix, or hit the F-11 500 during bootstrap.

**Item 9 (order bias) still live:** `main_use_cases` begins `["Home office", "Guest suite / short-term stay", …]`
and no "ignore the order of listed items" instruction exists anywhere in the prompt path.

**Cost note:** the Neo bootstrap default is **N=100 with Split** — 100 provider calls on first Run.
Dr. Wang manually lowered it to 20. For classroom use the default should be small.

**NOT VERIFIED in this pass** (form-level interaction): tag add/remove, field-level validation for invalid
min/max, ZIP placement behaviour, edit→save→refresh persistence, Reset Product Details local-vs-persisted,
URL autofill three-case provenance, Market backwards-click (item 6). These remain open.

## Stage 7 — Persona Preview vs Run: the grounding paths differ (confirmed)

| | Preview | Run |
|---|---|---|
| mode | **`heuristic_fallback`** | **`heuristic_only`** |
| warning | **"grounded priors unavailable; using heuristic fallback"** | **none** |
| `grounded_priors_available` | `False` | `False` |
| `prior_notes` | `[]` | — |

**Confirmed empirically: Preview warns, the Run does not.** A student who skips the preview never learns
that personas are un-grounded. This is the runtime proof of baseline §6.

Preview personas (N=3) were coherent: `Remote Professionals / strong / home office / unclear ROI / aware`,
`Wellness-Oriented / strong / wellness studio / unclear ROI / unaware`, etc. **They must not be described
as census-grounded** — no priors were loaded.

## Stage 8 — Run: counts PASS, live path NOT clean

```
executions (records/Q) : 6    expected 6     PASS
question-answer records: 192  expected 192   PASS
records per model      : 96 / 96             PASS
respondent ids         : RESP_001..003 reused across models   PASS (mirror alignment)
```

Diagnostics:
```
status                 : completed
truly_live_answers     : 189
fallback_answers       : 3
provider_error_count   : 0
malformed_json_count   : 0
live_answer_rate       : 0.984
persona_generation_mode: heuristic_only
warnings               : 1
```

**The desired happy path was `1.0 / 0 / 0 / 0`. Reality: 0.984 with 3 fabricated answers, with zero provider
errors and zero malformed JSON.** This is not forced green: it is the **silent coercion fallback** (F-04) —
answers the provider returned that failed exact option/range matching were discarded and replaced.

**I could not identify which 3 records were fabricated**, with full database access and the survey schema:
the mock generator emits schema-valid answers, and `MockResponseRecord` carries no provenance field. That is
the strongest available confirmation of F-04's labelling gap.

### Diagnostics visibility (requested table)

| Diagnostic | Backend / API | Visible to student? |
|---|---|---|
| Live answer rate (0.984) | **Yes** — run result **and** `analysis.run_debug_summary` | **NO** |
| Fallback count (3) | **Yes** | **Partial** — only inside the sentence *"fallback was used for 3 question(s)"* |
| Provider errors (0) | **Yes** | **NO** |
| Malformed JSON (0) | **Yes** | **NO** |
| Persona mode (`heuristic_only`) | **Yes** | **NO** |
| Warning details | **Yes** | **YES** — a `RUN WARNINGS` panel lists them |
| `transparency_note` | **Yes** — present in the analysis API | **NO** |

**Correction to the original reading of item 13:** the warnings *are* rendered, in a `RUN WARNINGS` panel,
and they carry counts. What is missing is the **rate**, the **failing model/question**, and the
**persona mode**. Item 13 is therefore **PARTIAL**, not "warnings are invisible".

## Stage 9 — Result

**Item 14 — Result drawing over Run: PASS (does not reproduce).** Measured geometry with the run completed
and all content expanded:
```
DOM order      : run-simulation -> analysis -> insights
run-simulation : docTop 18825  docBottom 22426
analysis       : docTop 22426  docBottom 39763
insights       : docTop 39763  docBottom 43854
all sections   : position relative, z-index auto, overflow visible, no transform
absolutely/fixed-positioned descendants escaping their section: 0
```
Sections tile exactly, boundary to boundary, with no intersection and nothing escaping. **Caveat:** Dr. Wang
observed the overlap during the Run→Result *transition* immediately after a run. That transient state was not
reproduced here and may be viewport- or timing-dependent, so this is *"does not reproduce in the settled
state at 1280×720"* rather than proof the transient cannot occur.

### Chart-vs-raw-record cross-check (3 questions)

| Q | Raw records (independent calc) | UI dashboard | Match |
|---|---|---|---|
| `S3` single_choice | `{Yes: 6}` | `Yes 6 (100.0%)`, others 0 | **EXACT** |
| `Q3` single_choice | `{Home office: 2, Wellness studio: 4}` | `Home office 2 (33.3%)`, `Wellness studio 4 (66.7%)` | **EXACT** |
| `Q1` likert | raw `[4,4,4,3,4,4]` mean **3.8333** | counts present but in **unlabelled numeric buckets** — see F-13 | **counts correct, presentation wrong** |

Analysis summary reports `total_records: 192`, `unique_respondents: 3`, `question_count: 32` — **the true
record count is available here**, and each card shows `6 RESPONSES` (correct).

**Direct on-screen contradiction:** the Run panel shows **`RESPONSES 3`** while the Result dashboard shows
**`6 RESPONSES`** per question over `192` total records — for the same run. This is F-05 reproduced in the UI.

**NOT VERIFIED:** model/segment filter behaviour and raw-record pagination were not exercised.
(The model filter control is present with `Overall Results`, `google/gemini-2.5-flash`, `openai/gpt-4o-mini`.)

## Stage 10 — Insights · Stage 11 — Interview

**NOT RUN in this session.** Neo Insights and the Neo Interview UI remain unverified in the browser.
Source- and API-level findings stand (F-06, F-07).

## Stage 10 — Insights (closed)

### Deterministic metrics vs raw records — **PASS**
| Displayed | Value | Independent recomputation | Match |
|---|---|---|---|
| Top intended use | `Wellness studio (gym, yoga, meditation)` **66.7%** | Q3 raw `{Wellness: 4, Home office: 2}` → 4/6 = 66.7% | **EXACT** |
| Average interest | **3.83** | Q1 raw `[4,4,4,3,4,4]` mean = **3.8333** | **EXACT** |
| Strongest / weakest segment | `Remote Professionals` / `Wellness-Oriented` | two distinct segments present; Neo IDs `Q0B/Q1/Q2` exist so `_segment_score_table` scores genuinely | **GENUINELY COMPUTED** |
| Charts | all 6 available (barrier 7 rows, ladder 4, message 5, model-diff 6, heatmap 8, use-case 2) | Neo survey supplies every required ID | **PASS** |

**On the Neo path Insights is arithmetically correct.** F-06 is a *generalization* defect, not a Neo defect.

### Caveat and diagnostic visibility — **FAIL**
| Item | In API | Visible in UI |
|---|---|---|
| `transparency_note` ("rule-based heuristics… validate with real respondents") | **Yes** | **NO** |
| "rule-based" / "heuristic" / "demo trust" wording | Yes | **NO** |
| "exploratory" / "validate with real respondents" | Yes | **NO** (lives in the collapsed Detailed Insights panel) |
| `live_answer_rate` (0.984) | **Not in the insights payload at all** (only in analysis) | **NO** |
| Fallback count | No | **NO** |
| `persona_generation_mode` (`heuristic_only`) | Yes (run) | **NO** |
| Confidence label | Yes | **Yes** |

The default Insights view opens with **"3 RESPONDENTS · 32 QUESTIONS"** and a *"reliability confidence read"* — and **no caveat of any kind**.

### LLM summary vs deterministic evidence — no contradiction, but it inherits the wrong count
5 key findings, every one carrying valid `evidence_ids` (`exec_top_use_case`, `exec_average_interest`, `exec_strongest_segment`, `barrier_1`, `concept_3`). Titles and values align with the deterministic layer — **no contradiction detected**.

However `result_reliability` reads: *"With only **3 respondents**…"*. The run produced **6 persona/model executions and 192 answers**. **F-05's ambiguous count propagates into the LLM's stated reliability judgement**, and the header repeats "3 RESPONDENTS".

## Stage 11 — Interview (closed)

### Live provider calls — **NONE**
The run returned **instantly** with 12 personas × 9 questions × 2 "models" = 216 answers. Backend job `job_b450320f79c9`.

### Fixture provenance — present in the backend, stripped before the client
```
backend result_json keys : demo_fixture, fixture_source, grounding_report, judge_model,
                           model_a, model_b, pairs, persona_count
  result['demo_fixture']    = True
  result['fixture_source']  = 'generated_fallback'
  result['judge_model']     = 'demo/stamp-fixture'
```
The client response contains only `job_id, status, persona_count, model_a, model_b, grounding_report, pairs, error, queued_at, completed_at`. **`demo_fixture`, `fixture_source` and `judge_model` are all removed by `_serialize_interview_job`.**

### What the student is shown
```
"Both AI models interview every persona independently. A judge LLM then scores agreement
 across four dimensions — STAMP-style — to flag low-reliability interviews before you rely on them."

"Dual-model verification: both LLMs interview every persona. A grounding score analogous to
 Krippendorff's α flags divergence before you proceed to research insights."

12 INTERVIEWS COMPLETE   ·   STAMP GROUNDING SCORE 100%   ·   PASSES THRESHOLD
Purchase Intent 100%  Primary Objection 100%  Fit-Tier Alignment 100%  Use-Case Specificity 100%
```
Interview Insights presents pre-written themes — *"Dedicated Space Reduces Friction"*, *"Value Proof Still Matters"* — as *"Mentioned by ~12 interviews"* with persona quotes.

Word-level scan of all three interview screens for `fixture / demo data / seeded / pre-generated / not live`: **zero matches.** Fabricated model IDs (`openai/gpt-4.1-mini`, `google/gemini-2.5-flash`) are returned by the API; they were not found as visible text in these three sections in this DOM state (they appear in transcript-source controls elsewhere).

### Answer to the question posed
**Yes — unambiguously.** A student is explicitly told two AI models interviewed each persona independently and that a judge LLM scored their agreement at **100%**, when in fact no model was called, "Model B" is Model A's text plus a fixed clause, and the "judge" is a lookup table on `fit_tier`. Nothing on screen contradicts that impression.

---

# OBSERVATIONAL BASELINE FROZEN — 2026-08-17
All Neo stages closed. Custom Study exercised through parser, live run, Result and Insights data paths.
Remaining browser gaps (Neo Audience/Product/Market form interactions, Custom form-by-form) are deferred to a
human-style smoke test on the Preview deployment after fixes.
