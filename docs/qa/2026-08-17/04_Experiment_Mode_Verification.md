# 04 — Experiment Mode Verification

**Target:** `yaza_Aug_work` @ `7645dfa` · Python 3.11.15
**Method:** direct invocation of `domain.execute_simulation_run`, then counting saved `response_records` at the data level — not reading UI numbers.

Notation: `N` base personas · `M` selected models · `R` reruns per persona · `Q` survey questions.

---

## 1. Specification

| Mode | Persona/model executions | Question-answer records | Model usage |
|---|---|---|---|
| **Split** | `N` | `N × Q` | each persona assigned one model, round-robin |
| **Mirror** | `N × M` | `N × M × Q` | every model answers for every persona; **respondent IDs align across models** |
| **Stability** | `N × R` | `N × R × Q` | **only the first selected model** generates responses |

Allocation source: `apps/api/src/adapters/legacy_backend/domain.py:426-439`.

```python
if config.experiment_mode == "mirror":
    for respondent_index in range(1, config.sample_size + 1):
        for model in config.selected_models:
            respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))
elif config.experiment_mode == "stability":
    model = config.selected_models[0]
    for respondent_index in range(1, config.sample_size + 1):
        for rerun in range(1, config.reruns_per_persona + 1):
            respondent_model_pairs.append((f"RESP_{respondent_index:03d}_R{rerun}", model, respondent_index, rerun))
else:  # split
    for respondent_index in range(1, config.sample_size + 1):
        model = config.selected_models[(respondent_index - 1) % len(config.selected_models)]
        respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))
```

Note there is a second, near-duplicate implementation in `legacy_runtime/backend/simulation/run_manager.py:307-321` that the API **never calls** (Streamlit-only). `domain._generate_response_records_compat` is dead code.

---

## 2. Verification run — N=4, M=2, Q=3

Survey: `Q1` single_choice (Yes/No/Maybe), `Q2` likert 1–5, `Q3` open_text.
Models: `openai/gpt-4o-mini`, `google/gemini-2.0-flash-001`.

| Mode | Expected exec | **Actual exec** | Expected records | **Actual records** | Models used | Verdict |
|---|---:|---:|---:|---:|---|---|
| split | 4 | **4** | 12 | **12** | both | **PASS** |
| mirror | 8 | **8** | 24 | **24** | both | **PASS** |
| stability (R=3) | 12 | **12** | 36 | **36** | **first model only** | **PASS** |

**Allocation logic is correct in all three modes.** Mirror reuses the identical `RESP_00i` across models and passes the same persona object (`domain.py:449`), so same-persona cross-model comparison is genuinely paired. Stability produces `RESP_001_R1`, `RESP_001_R2`, … and correctly ignores every model after the first.

---

## 3. Response-count discrepancy — the reporting layer is wrong

> **CLOSED** (`681dc4a`, `231f9c2`). The section below records the defect as found; it is no longer the
> product's behaviour. A run now reports `run_counts` with `personas`, `executions`, `questions` and
> `answer_records` named separately, and both totals carry the execution count. Verified on the release
> candidate `c64c797` with a live Neo mirror run at N=3, M=2, Q=32:
> `{"personas": 3, "executions": 6, "questions": 32, "answer_records": 192}` — reconciling with the 192
> stored rows, where the old tile would have shown **3**. All three modes are covered by parameterized
> tests, plus mirror respondent-id alignment and stability rerun encoding.

Three different numbers are all presented as "responses":

| Mode | True executions | True records | `total_generated_responses` | Distinct `respondent_id` (UI tile) |
|---|---:|---:|---:|---:|
| split | 4 | 12 | **4** | 4 |
| mirror | 8 | 24 | **4** ✗ | **4** ✗ |
| stability | 12 | 36 | **4** ✗ | 12 |

### Cause A — `total_generated_responses` is always `sample_size`
`domain._run_simulation_compat` (L228-241) finds no `run_simulation` on the legacy module and falls through to `run_mock_simulation`. `_call_with_supported_kwargs` (L207-225) then **silently drops the `records` kwarg** because that function does not accept it. `run_manager.run_mock_simulation` sets `total_generated = config.sample_size`.

Result: the field ignores models, reruns, questions, and whether any provider call succeeded.

### Cause B — the UI tile counts distinct respondent IDs
`run-simulation-section.tsx:643-673` (`getCompletedResponseCount`) builds a `Set` of `respondent_id`. Because Mirror **deliberately** reuses IDs across models, the tile returns `N` for both Split and Mirror, and `N × R` for Stability. It never returns `N × M` and never returns the record count.

**Consequence: Mirror is under-reported by a factor of M.** A 20-persona × 2-model × 32-question mirror run performs **40 executions** and stores **1,280 question-answer records**, while the run summary displays **20**.

Only the Analysis view exposes the truth, via `_compute_dataset_summary` → `unique_respondents` and `total_records`.

### Existing test codifies the wrong value
`apps/api/tests/test_legacy_live_simulation.py:146-148` asserts `total_generated_responses == 2` for a 2-persona × 2-model mirror run while also asserting `len(response_records) == 8`. The incorrect count is currently locked in as expected behaviour.

---

## 4. Related constraints observed

- **`sample_size` has no server-side upper bound** — `ExperimentPlan` validates only `gt=0`. The 1–50 cap applies solely to persona *preview*.
- **Split and Mirror require ≥2 models**; Stability also requires ≥2 selected but uses only the first — a UI/design constraint worth revisiting for classroom use.
- **No concurrency and no retries on the survey path**, with a 45 s per-call timeout, executed sequentially inside one HTTP request. A Mirror run at N=30, M=2 is 60 sequential calls — worst case ~45 minutes against Render's `maxShutdownDelaySeconds: 120`. The insights and interview paths, by contrast, do retry and use a thread pool.
- **Mirror ID reuse collides in the UI record table**: the React key is `${respondent_id}-${question_id}-${page}` (`run-simulation-section.tsx:514`), which is not unique for mirror runs.

---

## 5. Post-run Stability Check (distinct feature)

Not to be confused with Stability **mode**. The Result-page Stability Check reruns the *entire configured study* 2–5 times, regenerating personas each pass. It shares the daily provider-run quota. **Its real repeat loop has no automated test coverage** — `test_start_stability_check_endpoint_returns_saved_job` stubs `execute_stability_check` entirely.

---

## 6. Recommended regression tests (not yet written)

1. Assert executions and records for all three modes at the data level, parameterised over `N`, `M`, `R`, `Q`.
2. Assert Mirror respondent IDs are identical across models and map to the same persona.
3. Assert Stability IDs carry `_R{n}` suffixes and that only `selected_models[0]` appears.
4. Replace the assertion that locks `total_generated_responses == sample_size` with one asserting the intended semantics.
5. Assert the UI count helper against each mode's expected value.
