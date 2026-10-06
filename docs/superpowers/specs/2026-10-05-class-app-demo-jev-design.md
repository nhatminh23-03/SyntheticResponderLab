# Class app for Oct 7: survey demo, Jev, add-question form — design


### Context

Dr. Lin asked for two things for in-class testing on Wednesday, Oct 7:
- (a) a no-key, no-API, preloaded demo option;
- (b) Jev as the default synthetic-respondent live run, so students can add new questions.

Anderson builds demo mode on the interview and focus-group pages and deploys; Minh does the survey side.

**Decisions:**
- **Data shown:** synthetic results only.
- **Live engine:** Jev is the default; OpenRouter models stay selectable.
- **New questions:** an add-question form.
- **Demo access:** a demo button plus an automatic fallback.
- **Personas:** live runs use the app's persona generator.
- **Structure:** one run entry point with three sources.

**Measured quality, for labels:**
- Jev with drawing: TV 0.33, rank 0.28–0.34.
- R021 mix: TV 0.23, rank 0.51.

### 1. Run routing

- **Run request:** `POST …/simulation-runs` takes `source: live|demo` (default `live`).
- **Demo** is used when it is requested (the button always works), or when no key is configured. It makes no provider call and uses no quota, and its warnings give the reason.
- **Jev fails on every call:**
  - If the survey has **no** student-added questions → fall back to the demo with a very visible warning ("Jev is temporarily unavailable…").
  - If the survey **has** student-added questions → no substitution. The run stops with 503: "Jev is temporarily unavailable. Your new question requires a live run. You can retry or view the preloaded demo of the original survey." The UI offers Retry and the demo button.
- **Jev** is used for live runs with `typesafe/jev` alone. Jev with another model → 400.
- **OpenRouter:** everything else goes through the unchanged OpenRouter path.
- **Results:** every source gives the same result shape and `Job`, with `generation_mode` `demo_preloaded`, `jev_live` or `openrouter_live`.
- **Health payload:** adds `providers {jev, openrouter}` and `demo_available`.
- **Stability check:** stays live-only (409 with no key).

### 2. Preloaded demo data

- **Source:** R021 r1 (drawing-only four-model mix, 100 S1 Census personas, synthetic).
- **Builder:**
  - The script writes `demo_survey_fixture.json.gz`.
  - It validates personas and records against `main`'s schemas.
  - It records the source run and hashes.
  - It refuses driver columns and `aytm` paths.
  - It drops persona stories.
- **Loader:**
  - Keeps only the study survey's question ids (matched case-insensitively) and takes the first N personas.
  - Adds the demo warning.
  - Student-added questions → "Run live to answer these: …".
  - No shared ids → 409.

### 3. Jev engine

- **Request:** one `systemone` call per persona: `model: jev-latest`; `state: {respondent, stimulus}`; questions as score or choice.
  - The persona's `fit_tier`, `awareness_stage` and `persona_id` are left out.
- **Questions:**
  - the Q5 grid uses the grid anchors; other likert questions without labels use generic anchors;
  - multi-choice draws k options without replacement;
  - numeric and open text are not sent and get **no answers** (left missing, listed in a warning).
- **Answers:** score keys are shifted from 0 to 1–5; one seeded draw per (run, respondent, question); probabilities are kept.
- **Reliability:**
  - 8 calls at a time, 60-second timeout;
  - 408, 429 and 5xx are retried with backoff, 4 attempts; any other 4xx stops the run.
- **Rule: a Jev answer is kept, a Jev failure is missing.** Nothing is ever invented or filled in.
  - A respondent Jev failed on has no answer records. The run reports "N of M live respondents completed; K failed."
  - If more than 20% of respondents fail (`MAX_FAILED_SHARE = 0.20`), the run fails visibly (503, with the counts) so the instructor can retry.
  - If every respondent fails, see section 1.
- **Model list:** Jev is listed first with its label and is the default for the Neo study when configured. It counts toward the daily limit.

### 4. Frontend and editing

- **Run step:** buttons "Run live" and "Show preloaded demo (no AI)"; a demo banner; Run live is disabled with no key.
- **Experiment step:** the Jev default; mutual exclusion; Jev is listed first.
- **Survey step:** the "Add your own question" card (1–5 scale with editable anchors, or single choice with 2–8 options).
- **Endpoints:** add and remove; ids are `SQ1`, `SQ2`, …; only `SQ` ids can be removed.

### 5. Testing, coordination, deploy

- Test-first, with no network. API pytest, web build and unit tests must pass before every commit.
- One 1¢ live Jev check, only with OK.
- Anderson: readiness fields, PR Tuesday evening, he merges, sets the key on Render and deploys; smoke test Wednesday morning.
- If the Jev deploy slips, the demo still works with no key.
