# Class App (Survey Demo + Jev + Add-Question) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** By Wed Oct 7 the class app's survey flow has three working paths:
- a preloaded demo that needs no key and calls no AI;
- live runs on Jev as the default engine, with answers drawn from Jev's probabilities;
- an "Add your own question" form for students.

**Architecture:** One run entry point (`start_simulation_run`) chooses among three answer sources:
- the demo loader (a committed synthetic fixture);
- the new Jev engine;
- the existing OpenRouter path, unchanged.

All three return the same result dict and are saved as the same `Job`, so the run, analysis and insights pages work as they are. Provider availability is published in the health payload, and both the frontend and Anderson's pages read it there.

**Tech Stack:** FastAPI + SQLAlchemy + pydantic v2 (`apps/api`, Python ≥ 3.9); vendored legacy runtime (`apps/api/legacy_runtime`); Next.js 14 + TypeScript (`apps/web`); `node --test` for web unit tests; pytest for the API.

**Spec:** `docs/superpowers/specs/2026-10-05-class-app-demo-jev-design.md`.

## Global Constraints

- **Branch:** `feat/class-oct7-survey-demo-jev`, created from `origin/main`, in a separate worktree at `../SyntheticResponderLab-classapp`. Never commit on the research branch.
- **Commit messages:** no AI attribution (no `Co-Authored-By: Claude`, no "Generated with" lines).
- **Before every commit**, all of these must pass:
  - `cd apps/api && .venv/bin/python -m pytest -q`
  - `npm --prefix apps/web run build`
  - `npm --prefix apps/web run test:unit`
- **No real AYTM data in the repo:**
  - The fixture comes only from the synthetic R021 run.
  - The builder refuses any input with `driver_*` columns or `aytm` in its path.
- **`TYPESAFE_API_KEY` is server-side only:**
  - never logged, never returned in an API payload, never sent to the browser;
  - Anderson sets it on Render.
- **Error classes** (from `src.services.exceptions`):
  - `ValidationApiError` → 400
  - `ConflictApiError` → 409
  - `ProviderUnavailableApiError` → 503
- **Identifiers:**
  - Jev model id `"typesafe/jev"`; Jev API model name `"jev-latest"`; endpoint `https://api.typesafe.ai/v1/systemone`.
  - Generation modes: `demo_preloaded`, `jev_live`, `openrouter_live`.
  - Student question ids: `SQ1`, `SQ2`, …
- **UI copy:**
  - Demo button "Show preloaded demo (no AI)".
  - Jev label "Jev — fast, approximate (answers drawn from its probabilities)".
  - Demo warning: "Preloaded demo: answers saved from a run on 2026-10-03 (four models, answers drawn from their stated odds). No AI was called."
- **No paid API call** in any test. The only paid call is Task 10 step 3, about 1¢, and only with Minh's explicit OK at that time.
- **Provenance rules (2026-10-05 review):**
  - Live Jev runs never contain invented answers: a failed respondent or an unanswerable question is missing, and the counts are reported.
  - More than 20% of respondents failing fails the run.
  - Preloaded demo answers never stand in for a live run when the survey has student-added (`SQ`) questions.

## File map

| File | Responsibility |
| --- | --- |
| `apps/api/src/config/settings.py` (modify) | `typesafe_api_key`, `typesafe_base_url` |
| `apps/api/src/schemas/health.py`, `apps/api/src/services/health_service.py` (modify) | `providers`, `demo_available` in the health payload |
| `apps/api/scripts/build_demo_survey_fixture.py` (create) | research run folder → `demo_survey_fixture.json.gz` |
| `apps/api/src/services/demo_survey_fixture.json.gz` (create, generated) | 100 synthetic respondents (R021 r1) |
| `apps/api/src/services/demo_survey_run.py` (create) | fixture → standard run result for a study's survey |
| `apps/api/src/adapters/legacy_backend/jev_engine.py` (create) | Jev request building, transport, drawing, records |
| `apps/api/src/adapters/legacy_backend/domain.py` (modify) | Jev branch in `execute_simulation_run`; Jev entry in `list_model_catalog` |
| `apps/api/src/services/study_service.py` (modify) | `source` routing + demo fallback; `add_survey_question`, `remove_survey_question`; Jev default in the Neo bootstrap |
| `apps/api/src/schemas/study.py`, `apps/api/src/api/studies.py` (modify) | request models and endpoints |
| `apps/web/src/lib/{experiment-models,survey-question-form,demo-run}.ts` (create) | pure helpers, unit-tested |
| `apps/web/src/lib/api.ts`, `apps/web/src/lib/backend-readiness.ts`, `apps/web/src/app/api/readiness/route.ts` (modify) | calls and readiness passthrough |
| `apps/web/src/components/sections/{run-simulation,experiment,survey}-section.tsx` (modify), `add-question-card.tsx` (create) | UI |

---

### Task 0: Worktree, baseline, docs

**Files:**
- Create: `docs/superpowers/specs/2026-10-05-class-app-demo-jev-design.md` (copy of the Appendix).
- Create: `docs/superpowers/plans/2026-10-05-class-app-demo-jev.md` (copy of this plan without the Appendix).

- [ ] **Step 1: Create the worktree and install dependencies**

```bash
cd /Users/mnd/Desktop/SyntheticResponderLab/SyntheticResponderLab
git fetch origin
git worktree add ../SyntheticResponderLab-classapp -b feat/class-oct7-survey-demo-jev origin/main
cd ../SyntheticResponderLab-classapp/apps/api
python3 -m venv .venv && (.venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e . pytest)
cd ../web && npm ci
```

- [ ] **Step 2: Record the baseline. Expected: everything passes before any change.**

```bash
cd ../api && .venv/bin/python -m pytest -q | tail -1
cd .. && npm --prefix web run build >/dev/null && npm --prefix web run test:unit | tail -3
```

- [ ] **Step 3: Copy the spec and plan into `docs/superpowers/` and commit**

```bash
git add docs/superpowers && git commit -m "docs: spec and plan for the Oct 7 class app (survey demo, Jev, add-question form)"
```

---

### Task 1: Provider settings and health payload

**Files:**
- Modify: `apps/api/src/config/settings.py` (next to `openrouter_api_key`).
- Modify: `apps/api/src/schemas/health.py`.
- Modify: `apps/api/src/services/health_service.py` (`build_health_payload`, plus a new `_jev_check`).
- Test: `apps/api/tests/test_health.py`.

**Interfaces:**
- Produces: `AppSettings.typesafe_api_key: Optional[str]` and `AppSettings.typesafe_base_url: str`.
- Produces: `HealthPayload.providers: dict[str, bool]` with keys `jev` and `openrouter`, and `HealthPayload.demo_available: bool`.

- [ ] **Step 1: Write the failing tests** (append to `apps/api/tests/test_health.py`)

```python
def test_health_reports_providers_and_demo(client):
    body = client.get("/api/v1/health").json()["data"]
    assert body["providers"] == {"jev": False, "openrouter": False}
    assert body["demo_available"] is True
    assert body["checks"]["jev"]["status"] == "warn"


def test_health_reports_jev_when_key_set(test_settings):
    settings = test_settings.model_copy(update={"typesafe_api_key": "test-key"})
    session_factory = create_session_factory(settings)
    Base.metadata.create_all(bind=session_factory.kw["bind"])
    payload = build_health_payload(settings, session_factory)
    assert payload.providers == {"jev": True, "openrouter": False}
    assert "test-key" not in payload.model_dump_json()
```

- [ ] **Step 2: Run them. Expected: FAIL** (`providers` missing).

`cd apps/api && .venv/bin/python -m pytest tests/test_health.py -q`

- [ ] **Step 3: Implement**

`settings.py`, after `openrouter_base_url`:

```python
    typesafe_api_key: Optional[str] = Field(default=None, alias="TYPESAFE_API_KEY")
    typesafe_base_url: str = Field(default="https://api.typesafe.ai/v1/systemone", alias="TYPESAFE_BASE_URL")
```

`schemas/health.py`, `HealthPayload`:

```python
class HealthPayload(BaseModel):
    status: str
    checks: dict[str, HealthCheckResult]
    providers: dict[str, bool] = Field(default_factory=dict)
    demo_available: bool = True
```

`health_service.py`:
- Add `checks["jev"] = _jev_check(settings)` after the openrouter check.
- Return `HealthPayload(status=status, checks=checks, providers={"jev": bool(settings.typesafe_api_key), "openrouter": bool(settings.openrouter_api_key)}, demo_available=True)`.

```python
def _jev_check(settings: AppSettings) -> HealthCheckResult:
    if settings.typesafe_api_key:
        return HealthCheckResult(status="ok")
    return HealthCheckResult(status="warn", message="TYPESAFE_API_KEY missing; live Jev runs unavailable.")
```

- [ ] **Step 4: Run all API tests. Expected: PASS.**

`cd apps/api && .venv/bin/python -m pytest -q`

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/config/settings.py apps/api/src/schemas/health.py apps/api/src/services/health_service.py apps/api/tests/test_health.py
git commit -m "api: TYPESAFE settings, and providers + demo_available in the health payload"
```

---

### Task 2: Demo fixture builder and the committed fixture

**Files:**
- Create: `apps/api/scripts/build_demo_survey_fixture.py`.
- Create (generated): `apps/api/src/services/demo_survey_fixture.json.gz`.
- Test: `apps/api/tests/test_demo_survey_fixture_builder.py`.

**Interfaces:**
- Produces: `build_fixture(answers_long: Path, personas_csv: Path, run_label: str, run_date: str) -> dict`.
- The fixture format is:
  `{"source": {...}, "question_ids": [str], "models_used": [str], "respondents": [{"respondent_id": "RESP_001", "model": str, "persona": {PersonaProfile fields}, "answers": {question_id: value}}]}`.
  Respondents are in persona-file order.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "scripts"))
import build_demo_survey_fixture as builder  # noqa: E402

PERSONA_HEADER = ["persona_id", "age_bucket", "income_bucket", "ownership", "work_mode", "home_type", "lifestyle_tags",
                  "exact_age", "exact_household_income", "household_size", "story_headline"]


def _write(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _inputs(tmp_path: Path, extra_header=()):
    personas = _write(tmp_path / "personas.csv", PERSONA_HEADER + list(extra_header), [
        {"persona_id": "P001", "age_bucket": "30-34", "income_bucket": "$100k-$150k", "ownership": "owner", "work_mode": "remote",
         "home_type": "detached", "lifestyle_tags": "has kids;married", "exact_age": "47", "exact_household_income": "173405",
         "household_size": "3", "story_headline": "x", **{c: "v" for c in extra_header}},
        {"persona_id": "P002", "age_bucket": "45-54", "income_bucket": "$50k-$75k", "ownership": "renter", "work_mode": "commutes",
         "home_type": "detached", "lifestyle_tags": "", "exact_age": "29", "exact_household_income": "61000",
         "household_size": "1", "story_headline": "y", **{c: "v" for c in extra_header}},
    ])
    long_header = ["run_id", "model", "persona_id", "respondent_id", "question_id", "question_type", "answer", "answer_json", "is_fallback"]
    answers = _write(tmp_path / "answers_long.csv", long_header, [
        {"run_id": "r", "model": "qwen/qwen3.7-plus", "persona_id": "P001", "respondent_id": "RESP_001", "question_id": "Q1",
         "question_type": "likert", "answer": "4", "answer_json": "4", "is_fallback": "false"},
        {"run_id": "r", "model": "qwen/qwen3.7-plus", "persona_id": "P001", "respondent_id": "RESP_001", "question_id": "Q3",
         "question_type": "single_choice", "answer": "Home office", "answer_json": "\"Home office\"", "is_fallback": "false"},
        {"run_id": "r", "model": "google/gemini-3-flash-preview", "persona_id": "P002", "respondent_id": "RESP_002", "question_id": "Q1",
         "question_type": "likert", "answer": "1", "answer_json": "1", "is_fallback": "false"},
    ])
    return answers, personas


def test_build_fixture_shapes_respondents_in_persona_order(tmp_path):
    answers, personas = _inputs(tmp_path)
    fixture = builder.build_fixture(answers, personas, run_label="R021 r1", run_date="2026-10-03")
    assert fixture["question_ids"] == ["Q1", "Q3"]
    assert [r["respondent_id"] for r in fixture["respondents"]] == ["RESP_001", "RESP_002"]
    first = fixture["respondents"][0]
    assert first["model"] == "qwen/qwen3.7-plus" and first["answers"] == {"Q1": 4, "Q3": "Home office"}
    assert first["persona"]["persona_id"] == "P001"
    assert first["persona"]["age_bucket"] == "45-54"           # derived from exact_age 47, not the file label
    assert first["persona"]["income_bucket"] == "$150k-$200k"  # derived from exact income
    assert first["persona"]["lifestyle_tags"] == ["has kids", "married"]
    assert "story_headline" not in first["persona"]
    assert fixture["source"]["run_label"] == "R021 r1" and len(fixture["source"]["answers_sha256"]) == 64
    assert sorted(fixture["models_used"]) == ["google/gemini-3-flash-preview", "qwen/qwen3.7-plus"]


def test_refuses_driver_columns_and_real_data_paths(tmp_path):
    answers, personas = _inputs(tmp_path, extra_header=("prior_consideration_of_backyard_unit",))
    with pytest.raises(SystemExit):
        builder.build_fixture(answers, personas, run_label="x", run_date="2026-10-03")
    real_dir = tmp_path / "aytm_raw"
    real_dir.mkdir()
    clean_answers, clean_personas = _inputs(real_dir)
    with pytest.raises(SystemExit):
        builder.build_fixture(clean_answers, clean_personas, run_label="x", run_date="2026-10-03")


def test_main_writes_gzip(tmp_path):
    answers, personas = _inputs(tmp_path)
    out = tmp_path / "fixture.json.gz"
    assert builder.main(["--answers-long", str(answers), "--personas", str(personas), "--run-label", "R021 r1",
                         "--run-date", "2026-10-03", "--out", str(out)]) == 0
    assert json.loads(gzip.decompress(out.read_bytes()))["respondents"][1]["answers"] == {"Q1": 1}
```

- [ ] **Step 2: Run them. Expected: FAIL** (module missing).

`cd apps/api && .venv/bin/python -m pytest tests/test_demo_survey_fixture_builder.py -q`

- [ ] **Step 3: Implement `apps/api/scripts/build_demo_survey_fixture.py`**

```python
"""Build the preloaded survey-run demo from a saved research run. Synthetic data only.

    .venv/bin/python scripts/build_demo_survey_fixture.py \
        --answers-long "<Assets>/5_experiments/2026-10-02_R021_drawing_only_vs_drivers_only/survey_runs/<...>_mixed-panel_r1_s1-R021-draw-mixed/answers_long.csv" \
        --personas "<Assets>/4_persona_sets/matched_600_v2_S1-S6_2026-09-16/phase1_interview_matched600_s1.csv" \
        --run-label "R021 r1 (drawing only, four-model mix, S1)" --run-date 2026-10-03 \
        --out src/services/demo_survey_fixture.json.gz
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AGE_BANDS: List[Tuple[int, int, str]] = [(0, 17, "under 18"), (18, 24, "18-24"), (25, 29, "25-29"), (30, 34, "30-34"),
                                         (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64"), (65, 200, "65+")]
INCOME_BANDS: List[Tuple[int, int, str]] = [(0, 24_999, "<$25k"), (25_000, 49_999, "$25k-$50k"), (50_000, 74_999, "$50k-$75k"),
                                            (75_000, 99_999, "$75k-$100k"), (100_000, 149_999, "$100k-$150k"),
                                            (150_000, 199_999, "$150k-$200k"), (200_000, 299_999, "$200k-$300k"),
                                            (300_000, 499_999, "$300k-$500k"), (500_000, 10**12, "$500k+")]
PERSONA_FIELDS = ["persona_id", "age_bucket", "income_bucket", "household_size_bucket", "ownership", "home_type", "work_mode",
                  "lifestyle_tags", "likely_use_case", "likely_barrier", "segment_label", "affordability_pressure"]
DRIVER_COLUMNS = {"prior_consideration_of_backyard_unit", "outdoor_recreation_frequency", "member_of_outdoor_club",
                  "most_likely_use_for_a_backyard_unit"}


def _refuse(message: str) -> None:
    print(f"REFUSED: {message}", file=sys.stderr)
    raise SystemExit(3)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _band(value: Optional[str], bands: List[Tuple[int, int, str]]) -> Optional[str]:
    try:
        number = int(float(value or ""))
    except ValueError:
        return None
    return next((label for low, high, label in bands if low <= number <= high), None)


def _clean(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    return text or None


def persona_from_row(row: Dict[str, str]) -> Dict[str, object]:
    persona: Dict[str, object] = {field: _clean(row.get(field)) for field in PERSONA_FIELDS}
    persona["age_bucket"] = _band(row.get("exact_age"), AGE_BANDS) or persona["age_bucket"]
    persona["income_bucket"] = _band(row.get("exact_household_income"), INCOME_BANDS) or persona["income_bucket"]
    size = _clean(row.get("household_size"))
    persona["household_size_bucket"] = persona["household_size_bucket"] or (f"{size} person(s)" if size else None)
    persona["lifestyle_tags"] = [tag.strip() for tag in (row.get("lifestyle_tags") or "").split(";") if tag.strip()]
    return persona


def build_fixture(answers_long: Path, personas_csv: Path, *, run_label: str, run_date: str) -> dict:
    for path in (answers_long, personas_csv):
        if "aytm" in str(Path(path).resolve()).lower():
            _refuse(f"{path} looks like real-respondent material")
    with open(personas_csv, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        drivers = [c for c in (reader.fieldnames or []) if c in DRIVER_COLUMNS or c.startswith("driver_")]
        if drivers:
            _refuse(f"{personas_csv} carries driver columns {drivers}; the demo is synthetic only")
        persona_rows = list(reader)
    answers: Dict[str, Dict[str, object]] = {}
    models: Dict[str, str] = {}
    question_ids: List[str] = []
    with open(answers_long, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            pid, qid = row["persona_id"], row["question_id"]
            if qid not in question_ids:
                question_ids.append(qid)
            models[pid] = row["model"]
            answers.setdefault(pid, {})[qid] = json.loads(row["answer_json"]) if row.get("answer_json") else row["answer"]
    respondents = []
    for row in persona_rows:
        pid = row["persona_id"]
        if pid not in answers:
            continue
        respondents.append({"respondent_id": f"RESP_{len(respondents) + 1:03d}", "model": models[pid],
                            "persona": persona_from_row(row), "answers": answers[pid]})
    return {
        "source": {"run_label": run_label, "run_date": run_date, "answers_file": Path(answers_long).name,
                   "answers_sha256": _sha256(Path(answers_long)), "personas_sha256": _sha256(Path(personas_csv))},
        "question_ids": question_ids,
        "models_used": sorted(set(models.values())),
        "respondents": respondents,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers-long", type=Path, required=True)
    parser.add_argument("--personas", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    fixture = build_fixture(args.answers_long, args.personas, run_label=args.run_label, run_date=args.run_date)
    args.out.write_bytes(gzip.compress(json.dumps(fixture, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(f"wrote {len(fixture['respondents'])} respondents x {len(fixture['question_ids'])} questions to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests. Expected: PASS.**

- [ ] **Step 5: Generate the real fixture from R021 r1.** Expected: "wrote 100 respondents x 39 questions", file under about 1 MB.

```bash
A=/Users/mnd/Desktop/SyntheticResponderLab/SyntheticResponderLab-Assets
RUN=$(ls -d $A/5_experiments/2026-10-02_R021_drawing_only_vs_drivers_only/survey_runs/*mixed-panel_r1_s1-R021-draw-mixed)
.venv/bin/python scripts/build_demo_survey_fixture.py --answers-long "$RUN/answers_long.csv" \
  --personas "$A/4_persona_sets/matched_600_v2_S1-S6_2026-09-16/phase1_interview_matched600_s1.csv" \
  --run-label "R021 r1 (drawing only, four-model mix, S1)" --run-date 2026-10-03 \
  --out src/services/demo_survey_fixture.json.gz
ls -la src/services/demo_survey_fixture.json.gz
```

- [ ] **Step 6: Run the full API tests, then commit**

```bash
git add apps/api/scripts/build_demo_survey_fixture.py apps/api/src/services/demo_survey_fixture.json.gz apps/api/tests/test_demo_survey_fixture_builder.py
git commit -m "api: preloaded survey demo fixture built from the synthetic R021 run (no real data)"
```

---

### Task 3: Demo loader

**Files:**
- Create: `apps/api/src/services/demo_survey_run.py`.
- Test: `apps/api/tests/test_demo_survey_run.py`.

**Interfaces:**
- Consumes: the fixture file from Task 2.
- Produces: `build_demo_run_result(*, survey_payload: dict, experiment_payload: dict, reason: str, detail: Optional[str] = None, fixture: Optional[dict] = None) -> dict`.
  - `reason` is one of `"requested"`, `"no_key"`, `"jev_unavailable"`.
  - Raises `ConflictApiError` when no question matches the fixture.
- Produces: `DEMO_WARNING` (str) and `NOT_COVERED_MESSAGE` (str).

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import pytest

from src.services.demo_survey_run import DEMO_WARNING, NOT_COVERED_MESSAGE, build_demo_run_result, load_fixture
from src.services.exceptions import ConflictApiError

FIXTURE = {
    "source": {"run_label": "R021 r1", "run_date": "2026-10-03"},
    "question_ids": ["Q1", "Q0B"],
    "models_used": ["a/m1", "b/m2"],
    "respondents": [
        {"respondent_id": "RESP_001", "model": "a/m1", "persona": {"persona_id": "P001", "lifestyle_tags": []}, "answers": {"Q1": 4, "Q0B": 2}},
        {"respondent_id": "RESP_002", "model": "b/m2", "persona": {"persona_id": "P002", "lifestyle_tags": []}, "answers": {"Q1": 1, "Q0B": 3}},
    ],
}
SURVEY = {"survey_title": "Tahoe Mini", "questions": [
    {"id": "Q1", "text": "Purchase interest", "question_type": "likert", "options": []},
    {"id": "Q0b", "text": "Category interest", "question_type": "likert", "options": []},
    {"id": "SQ1", "text": "Would you paint it?", "question_type": "single_choice", "options": ["Yes", "No"]},
]}


def test_demo_result_follows_the_survey_and_sample_size():
    result = build_demo_run_result(survey_payload=SURVEY, experiment_payload={"sample_size": 1}, reason="requested", fixture=FIXTURE)
    assert result["generation_mode"] == "demo_preloaded" and result["status"] == "completed"
    assert [p["persona_id"] for p in result["personas"]] == ["P001"]
    assert [(r["question_id"], r["answer"], r["question_text"]) for r in result["response_records"]] == [
        ("Q1", 4, "Purchase interest"), ("Q0b", 2, "Category interest")]   # ids match case-insensitively
    assert all(r["is_fallback"] is False and r["respondent_id"] == "RESP_001" for r in result["response_records"])
    assert result["warnings"][0] == DEMO_WARNING
    assert any("SQ1" in w for w in result["warnings"])
    assert result["run_counts"] == {"personas": 1, "executions": 1, "questions": 3, "answer_records": 2}


@pytest.mark.parametrize("reason, phrase", [("no_key", "No AI key"), ("jev_unavailable", "Jev is temporarily unavailable")])
def test_demo_reason_is_stated(reason, phrase):
    result = build_demo_run_result(survey_payload=SURVEY, experiment_payload={"sample_size": 5}, reason=reason, fixture=FIXTURE)
    assert any(phrase in w for w in result["warnings"])
    assert len(result["personas"]) == 2


def test_survey_without_shared_questions_is_refused():
    with pytest.raises(ConflictApiError) as error:
        build_demo_run_result(survey_payload={"questions": [{"id": "C1", "text": "x", "question_type": "likert"}]},
                              experiment_payload={}, reason="requested", fixture=FIXTURE)
    assert error.value.message == NOT_COVERED_MESSAGE


def test_committed_fixture_is_synthetic_and_complete():
    fixture = load_fixture()
    assert len(fixture["respondents"]) == 100 and "Q1" in fixture["question_ids"]
    text = str(fixture).lower()
    assert "aytm" not in text and "driver_donor_id" not in text and "prior_consideration" not in text
```

- [ ] **Step 2: Run them. Expected: FAIL** (module missing).

- [ ] **Step 3: Implement `apps/api/src/services/demo_survey_run.py`**

```python
"""The preloaded survey-run demo: answers saved from a synthetic run, served with no provider call."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.exceptions import ConflictApiError

FIXTURE_PATH = Path(__file__).with_name("demo_survey_fixture.json.gz")
DEMO_WARNING = ("Preloaded demo: answers saved from a run on 2026-10-03 (four models, answers drawn from their stated odds). "
                "No AI was called.")
NOT_COVERED_MESSAGE = "The preloaded demo covers the Tahoe Mini survey; use a live run for this survey."
REASONS = {
    "requested": "You chose the preloaded demo.",
    "no_key": "No AI key is configured on this server, so the preloaded demo was shown instead of a live run.",
    "jev_unavailable": ("Jev is temporarily unavailable, so these are the PRELOADED DEMO answers from 2026-10-03, "
                        "not a live run. Retry to get live answers."),
}


@lru_cache(maxsize=1)
def load_fixture(path: str = str(FIXTURE_PATH)) -> Dict[str, Any]:
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def build_demo_run_result(*, survey_payload: Dict[str, Any], experiment_payload: Dict[str, Any], reason: str,
                          detail: Optional[str] = None, fixture: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fixture = fixture if fixture is not None else load_fixture()
    available = {qid.upper(): qid for qid in fixture["question_ids"]}
    questions: List[Dict[str, Any]] = list(survey_payload.get("questions") or [])
    covered = [q for q in questions if str(q.get("id", "")).upper() in available]
    if not covered:
        raise ConflictApiError(NOT_COVERED_MESSAGE)
    missing = [q["id"] for q in questions if str(q.get("id", "")).upper() not in available]
    sample = max(1, min(int(experiment_payload.get("sample_size") or len(fixture["respondents"])), len(fixture["respondents"])))
    respondents = fixture["respondents"][:sample]
    run_id = f"DEMO_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    survey_title = survey_payload.get("survey_title")
    records: List[Dict[str, Any]] = []
    for respondent in respondents:
        for question in covered:
            answer = respondent["answers"].get(available[str(question["id"]).upper()])
            if answer is None:
                continue
            records.append({"respondent_id": respondent["respondent_id"], "model": respondent["model"], "experiment_mode": "split",
                            "survey_title": survey_title, "question_id": question["id"], "question_text": question.get("text") or "",
                            "question_type": question.get("question_type") or "", "answer": answer, "segment_label": None,
                            "run_id": run_id, "is_fallback": False})
    warnings = [DEMO_WARNING, REASONS.get(reason, REASONS["requested"])]
    if detail:
        warnings.append(f"Detail: {detail}")
    if missing:
        warnings.append(f"Run live to answer these: {', '.join(missing)}")
    models_used = sorted({r["model"] for r in respondents})
    return {
        "run_id": run_id, "status": "completed",
        "run_counts": {"personas": len(respondents), "executions": len(respondents), "questions": len(questions), "answer_records": len(records)},
        "total_requested_responses": len(respondents), "total_generated_responses": len(respondents),
        "models_used": models_used, "experiment_mode": "split", "survey_title": survey_title, "question_count": len(questions),
        "notes": f"Preloaded demo from {fixture['source'].get('run_label')}.", "created_at": datetime.now(timezone.utc).isoformat(),
        "generation_mode": "demo_preloaded", "provider_model_name": None, "persona_generation_mode": "preloaded_s1",
        "grounded_priors_available": False, "cex_affordability_available": False, "geography_context": None, "prior_notes": [],
        "warnings": warnings,
        "generation_debug": {"generation_mode": "demo_preloaded", "executions": len(respondents), "answer_records": len(records),
                             "questions_total": len(records), "request_errors": 0, "provider_error_count": 0,
                             "malformed_json_count": 0, "questions_fallback_to_mock": 0, "questions_parsed_from_live": 0},
        "run_debug_summary": {},
        "run_conditions": {"context_influence": {"enabled": False, "sources": []}, "generation_mode": "demo_preloaded",
                           "selected_models": models_used},
        "personas": [r["persona"] for r in respondents],
        "response_records": records, "response_record_preview": records[:24],
        "survey_parse_warnings": list(survey_payload.get("parse_warnings", [])),
        "demo": {"reason": reason, "source": fixture["source"]},
    }
```

- [ ] **Step 4: Run the tests. Expected: PASS.** Then run the full API suite.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/services/demo_survey_run.py apps/api/tests/test_demo_survey_run.py
git commit -m "api: demo loader turns the preloaded fixture into a standard run result for the study's survey"
```

---

### Task 4: Run routing with `source` and the automatic demo fallback

**Files:**
- Modify: `apps/api/src/schemas/study.py:163` (`SimulationRunRequest`).
- Modify: `apps/api/src/api/studies.py:545` (pass `source`).
- Modify: `apps/api/src/services/study_service.py:1165` (`start_simulation_run`).
- Test: `apps/api/tests/test_simulation_run_source.py`.

**Interfaces:**
- Consumes: `build_demo_run_result` (Task 3), and `JevUnavailableError` from `src.adapters.legacy_backend.jev_engine` (Task 5).
  - For this task, create `jev_engine.py` containing only the error classes shown in Task 5 Step 3. Task 5 fills in the rest.
- Produces: `start_simulation_run(session, settings, study, *, prompt_user_template_override=None, source="live")`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from tests.test_studies_endpoints import _create_ready_to_run_study


def _fail_if_called(**kwargs):
    raise AssertionError("a provider was called")


def test_demo_source_never_calls_a_provider_and_renders_analysis(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"})
    assert response.status_code == 200
    result = response.json()["data"]["simulation_run"]["result"]
    assert result["generation_mode"] == "demo_preloaded" and result["demo"]["reason"] == "requested"
    assert not any("Run live to answer" in w for w in result["warnings"])   # the Neo preset is fully covered
    assert client.get(f"/api/v1/studies/{study_id}/analysis").status_code == 200
    assert client.get(f"/api/v1/studies/{study_id}/insights").status_code == 200


def test_live_without_any_key_falls_back_to_demo(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    result = client.post(f"/api/v1/studies/{study_id}/simulation-runs").json()["data"]["simulation_run"]["result"]
    assert result["demo"]["reason"] == "no_key"


def _jev_down(**kwargs):
    from src.adapters.legacy_backend.jev_engine import JevUnavailableError
    raise JevUnavailableError("Jev did not answer any respondent: timeout")


def test_jev_down_on_the_original_survey_falls_back_to_demo_visibly(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service._live_engine_configured", lambda settings: True)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _jev_down)
    result = client.post(f"/api/v1/studies/{study_id}/simulation-runs").json()["data"]["simulation_run"]["result"]
    assert result["demo"]["reason"] == "jev_unavailable"
    assert any("Jev is temporarily unavailable" in w for w in result["warnings"])


def test_jev_down_with_a_student_question_is_not_replaced_by_demo_answers(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    # Task 7's endpoint does not exist yet; append a student question through the existing "accept survey" endpoint.
    study = client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]
    survey = dict(study["survey"]["value"])
    survey["questions"] = survey["questions"] + [{"id": "SQ1", "text": "Would solar panels make this product more appealing?",
                                                  "question_type": "likert", "options": ["1", "2", "3", "4", "5"],
                                                  "min_value": 1, "max_value": 5, "required": True}]
    assert client.post(f"/api/v1/studies/{study_id}/survey/generated", json={"survey_schema": survey}).status_code == 200
    monkeypatch.setattr("src.services.study_service._live_engine_configured", lambda settings: True)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _jev_down)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 503
    assert "Your new question requires a live run" in response.text
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest is None or latest["status"] == "failed"   # no demo answers were saved for this run


def test_unknown_source_is_rejected(client):
    study_id = _create_ready_to_run_study(client)
    assert client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "fake"}).status_code in (400, 422)
```

- [ ] **Step 2: Run them. Expected: FAIL.**

- [ ] **Step 3: Implement**

`schemas/study.py`:

```python
class SimulationRunRequest(BaseModel):
    prompt_user_template: Optional[str] = None
    source: Literal["live", "demo"] = "live"
```

(`Literal` is already imported in that file; if not, add it to the typing import.)

`api/studies.py`, in `start_simulation_run_endpoint`: add the keyword `source=(payload.source if payload else "live")` to the `start_simulation_run(...)` call.

`study_service.py`:
- Imports:

```python
from src.adapters.legacy_backend.jev_engine import JevUnavailableError
from src.services.demo_survey_run import build_demo_run_result
```

- Add a helper above `start_simulation_run`:

```python
JEV_DOWN_WITH_STUDENT_QUESTIONS = ("Jev is temporarily unavailable. Your new question requires a live run. "
                                   "You can retry or view the preloaded demo of the original survey.")


def _live_engine_configured(settings: AppSettings) -> bool:
    return bool(settings.openrouter_api_key or settings.typesafe_api_key)


def _is_student_question(question_id: str) -> bool:
    return question_id.startswith("SQ") and question_id[2:].isdigit()
```

(Add `ProviderUnavailableApiError` to the `src.services.exceptions` import in `study_service.py`. Task 7 later reuses `_is_student_question` in `remove_survey_question`, replacing its inline check.)

- Edit `start_simulation_run`:
  - Add the parameter `source: str = "live"`.
  - After the three "must be saved" checks, insert:

```python
    if source not in {"live", "demo"}:
        raise ValidationApiError("source must be 'live' or 'demo'.")
    demo_reason = "requested" if source == "demo" else (None if _live_engine_configured(settings) else "no_key")
```

  - Wrap the existing `assert_no_in_flight_provider_job(...)`, the quota block and the geography lookup in `if demo_reason is None:`. The geography variables default to `None` first.
  - Replace the body of the `try:` that calls `execute_simulation_run(...)` with:

```python
        if demo_reason is not None:
            result = build_demo_run_result(survey_payload=survey, experiment_payload=experiment, reason=demo_reason)
        else:
            try:
                result = execute_simulation_run(
                    settings=settings, audience_payload=audience, survey_payload=survey, experiment_payload=experiment,
                    product_payload=product, market_payload=market, geography_context=geography_context,
                    prompt_user_template_override=normalized_prompt_override,
                )
            except JevUnavailableError as exc:
                if any(_is_student_question(q.get("id", "")) for q in survey.get("questions", [])):
                    # A student's own question cannot be answered from saved demo data: stop, don't substitute.
                    raise ProviderUnavailableApiError(JEV_DOWN_WITH_STUDENT_QUESTIONS, details={"retry": True, "demo_available": True}) from exc
                result = build_demo_run_result(survey_payload=survey, experiment_payload=experiment,
                                               reason="jev_unavailable", detail=exc.message)
            if geography_warning:
                result.setdefault("warnings", []).append(geography_warning)
```

  - Add `"source": source` to the Job's `payload_json`.

- [ ] **Step 4: Run the tests, then the full suite. Expected: PASS.** The existing run tests are unaffected, because they monkeypatch `execute_simulation_run`; with no key they would now be routed to demo.
  - If an existing test expects `execute_simulation_run` to be called with no key, monkeypatch `src.services.study_service._live_engine_configured` to `lambda s: True` in that test.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/schemas/study.py apps/api/src/api/studies.py apps/api/src/services/study_service.py apps/api/src/adapters/legacy_backend/jev_engine.py apps/api/tests/test_simulation_run_source.py
git commit -m "api: simulation runs take source=live|demo; demo when asked, when no key is set, or when Jev is down"
```

---

### Task 5: Jev engine

**Files:**
- Create or fill: `apps/api/src/adapters/legacy_backend/jev_engine.py`.
- Test: `apps/api/tests/test_jev_engine.py`.

**Interfaces:**
- Produces: `JEV_MODEL_ID = "typesafe/jev"` and `MAX_FAILED_SHARE = 0.20`.
- Produces three error classes, all `ProviderUnavailableApiError` subclasses:
  - `JevUnavailableError`: every respondent failed;
  - `JevRequestError`: Jev refused the request (non-retryable 4xx);
  - `JevTooManyFailuresError`: more than 20% of respondents failed.
- Produces: `build_questions(questions) -> (dict, list[str])`, `answer_value(question, probabilities, key) -> Any`, `http_transport(api_key, url, *, timeout=60, retries=4, sleep=time.sleep) -> Callable[[dict], dict]`.
- Produces: `generate_jev_records(*, schemas, config, survey_schema, persona_profiles, business_product_context, market_context, transport, max_concurrency) -> (records, generation_debug, record_is_fallback, answer_probabilities)`.
  - A Jev answer is kept; a failure is missing; nothing is filled in.
  - `record_is_fallback` is all `False`.
  - The debug dict carries `respondents_completed`, `respondents_failed`, `questions_missing` and `jev_warnings`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.adapters.legacy_backend import jev_engine as jev


def Q(id, question_type, options=(), min_value=None, max_value=None):
    return SimpleNamespace(id=id, text=f"text {id}", question_type=question_type, options=list(options),
                           min_value=min_value, max_value=max_value, model_dump=lambda: {})


def test_build_questions_maps_types_and_skips_open_ones():
    questions = [Q("Q1", "likert", ["a", "b", "c", "d", "e"]), Q("Q5_1", "likert", [], 1, 5), Q("Q3", "single_choice", ["Office", "Gym"]),
                 Q("Q20", "multi_choice", ["Ads", "Expo", "Friends"]), Q("Q8", "open_text"), Q("Q9", "numeric")]
    built, skipped = jev.build_questions(questions)
    assert built["Q1"] == {"type": "score", "instructions": "text Q1", "criteria": ["a", "b", "c", "d", "e"]}
    assert built["Q5_1"]["criteria"] == list(jev.GRID_ANCHORS)
    assert built["Q3"] == {"type": "choice", "instructions": "text Q3", "criteria": {"Office": "Office", "Gym": "Gym"}}
    assert built["Q20"]["type"] == "choice"
    assert skipped == ["Q8", "Q9"]


def test_score_keys_are_shifted_and_draws_repeat_with_the_same_key():
    likert = Q("Q1", "likert", ["a", "b", "c", "d", "e"])
    probabilities = jev.probabilities_for({"type": "score", "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0, "4": 1.0}})
    assert probabilities == {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 1.0}
    assert jev.answer_value(likert, probabilities, "run:P1:Q1") == 5
    spread = jev.probabilities_for({"type": "score", "probabilities": {str(i): 0.2 for i in range(5)}})
    assert jev.answer_value(likert, spread, "run:P1:Q1") == jev.answer_value(likert, spread, "run:P1:Q1")
    multi = Q("Q20", "multi_choice", ["Ads", "Expo", "Friends"])
    picks = jev.answer_value(multi, {"Ads": 0.5, "Expo": 0.3, "Friends": 0.2}, "k")
    assert isinstance(picks, list) and len(picks) == 2 and len(set(picks)) == 2


def test_http_transport_retries_then_raises_and_never_leaks_the_key(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(request, timeout, context=None):
        calls.append(request)
        if len(calls) < 3:
            import urllib.error, io
            raise urllib.error.HTTPError(request.full_url, 429, "busy", {}, io.BytesIO(b"slow down"))
        return Resp(json.dumps({"answers": {}}).encode())

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    send = jev.http_transport("secret-key", "https://example.invalid", sleep=lambda s: None)
    assert send({"model": "jev-latest"}) == {"answers": {}}
    assert len(calls) == 3

    def unauthorized(request, timeout, context=None):
        import urllib.error, io
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(jev.urllib.request, "urlopen", unauthorized)
    with pytest.raises(jev.JevRequestError) as error:
        jev.http_transport("secret-key", "https://example.invalid", sleep=lambda s: None)({})
    assert "secret-key" not in error.value.message


def _stub_runtime(n_personas=2):
    schemas = SimpleNamespace(MockResponseRecord=lambda **kw: SimpleNamespace(**kw))
    config = SimpleNamespace(run_id="RUN_X", experiment_mode="split", survey_title="T", sample_size=n_personas,
                             selected_models=[jev.JEV_MODEL_ID])
    def persona(i, age):
        return SimpleNamespace(persona_id=f"P{i}", segment_label=None,
                               model_dump=lambda **kw: {"persona_id": f"P{i}", "age_bucket": age, "fit_tier": "strong"})
    personas = [persona(i, "45-54" if i == n_personas else "30-34") for i in range(1, n_personas + 1)]
    survey = SimpleNamespace(questions=[Q("Q1", "likert", ["a", "b", "c", "d", "e"]), Q("Q8", "open_text")], description=None)
    return schemas, config, personas, survey


def _transport_failing_on(age, sent):
    def transport(payload):
        sent.append(payload)
        if payload["state"]["respondent"].get("age_bucket") == age:
            raise RuntimeError("timeout")
        return {"answers": {"Q1": {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1, "4": 0}}}}
    return transport


def test_failed_respondents_and_unsupported_questions_are_missing_never_invented():
    schemas, config, personas, survey = _stub_runtime(n_personas=5)   # the last persona fails: 1 of 5 = 20%, allowed
    sent = []
    records, debug, is_fallback, probabilities = jev.generate_jev_records(
        schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
        business_product_context=None, market_context=None, transport=_transport_failing_on("45-54", sent), max_concurrency=2)
    assert [(r.respondent_id, r.question_id, r.answer) for r in records] == [(f"RESP_00{i}", "Q1", 4) for i in range(1, 5)]
    assert is_fallback == [False] * 4                       # nothing filled in: no Q8 rows, no rows for RESP_005
    assert debug["respondents_completed"] == 4 and debug["respondents_failed"] == 1
    assert "4 of 5 live respondents completed; 1 failed." in debug["jev_warnings"]
    assert any("Q8" in w for w in debug["jev_warnings"])
    assert all("fit_tier" not in p["state"]["respondent"] and "persona_id" not in p["state"]["respondent"] for p in sent)
    assert probabilities["RESP_001"]["Q1"]["4"] == 1 and "RESP_005" not in probabilities


def test_more_than_a_fifth_failing_fails_the_run_visibly():
    schemas, config, personas, survey = _stub_runtime(n_personas=2)   # 1 of 2 = 50% failed
    with pytest.raises(jev.JevTooManyFailuresError) as error:
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None,
                                 transport=_transport_failing_on("45-54", []), max_concurrency=2)
    assert "1 of 2" in error.value.message and "retry" in error.value.message.lower()


def test_all_respondents_failing_raises_unavailable():
    schemas, config, personas, survey = _stub_runtime()

    def transport(payload):
        raise RuntimeError("down")

    with pytest.raises(jev.JevUnavailableError):
        jev.generate_jev_records(schemas=schemas, config=config, survey_schema=survey, persona_profiles=personas,
                                 business_product_context=None, market_context=None, transport=transport, max_concurrency=2)
```

- [ ] **Step 2: Run them. Expected: FAIL.**

- [ ] **Step 3: Implement `apps/api/src/adapters/legacy_backend/jev_engine.py`**

```python
"""Live survey answers from TypeSafe's Jev classifier, one answer drawn per question from its probabilities.

Ported from research/neo_persona_set/phase3/jev_survey.py. Jev answers each question in isolation and
returns a probability per option; we draw one answer at those odds, seeded per run, respondent and
question, so a rerun repeats and the panel keeps Jev's spread instead of its single safest guess.
"""
from __future__ import annotations

import json
import random
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.services.exceptions import ProviderUnavailableApiError

JEV_MODEL_ID = "typesafe/jev"
JEV_API_MODEL = "jev-latest"
GRID_ANCHORS = ("Would not reduce my likelihood at all", "Would reduce my likelihood slightly",
                "Would reduce my likelihood moderately", "Would reduce my likelihood a lot", "Would strongly reduce my likelihood")
GENERIC_ANCHORS = ("1 - lowest", "2", "3", "4", "5 - highest")
PERSONA_EXCLUDED = {"persona_id", "fit_tier", "awareness_stage"}   # fit_tier is scored after, never prompted (SPEC P0.2)
RETRYABLE = {408, 429}

try:
    import certifi
    _SSL: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = None


class JevUnavailableError(ProviderUnavailableApiError):
    """Jev answered no respondent (network, timeouts, 5xx): the run falls back to the preloaded demo."""


class JevRequestError(ProviderUnavailableApiError):
    """Jev refused the request (bad key, bad payload): the run stops with this message."""


class JevTooManyFailuresError(ProviderUnavailableApiError):
    """More than MAX_FAILED_SHARE of respondents failed: the run fails visibly so the instructor can retry."""


MAX_FAILED_SHARE = 0.20


Transport = Callable[[Dict[str, Any]], Dict[str, Any]]


def http_transport(api_key: str, url: str, *, timeout: int = 60, retries: int = 4,
                   sleep: Callable[[float], None] = time.sleep) -> Transport:
    def send(payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode()
        last: Optional[Exception] = None
        for attempt in range(retries):
            request = urllib.request.Request(url, data=body, method="POST",
                                             headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=_SSL) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")[:200].replace(api_key, "***")
                if error.code not in RETRYABLE and error.code < 500:
                    raise JevRequestError(f"Jev refused the request (HTTP {error.code}): {detail}") from None
                last = RuntimeError(f"HTTP {error.code}")
            except Exception as error:  # noqa: BLE001 - retried below
                last = error
            if attempt < retries - 1:
                sleep(2 ** attempt)
        raise RuntimeError(f"Jev request failed after {retries} attempts: {last}")
    return send


def build_questions(questions: List[Any]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    built: Dict[str, Dict[str, Any]] = {}
    skipped: List[str] = []
    for question in questions:
        text = " ".join(str(question.text or "").split())
        options = list(question.options or [])
        if question.question_type == "likert":
            if len(options) != 5:
                options = list(GRID_ANCHORS if str(question.id).upper().startswith("Q5_") else GENERIC_ANCHORS)
            built[question.id] = {"type": "score", "instructions": text, "criteria": options}
        elif question.question_type in {"single_choice", "multi_choice"} and options:
            built[question.id] = {"type": "choice", "instructions": text, "criteria": {o: o for o in options}}
        else:
            skipped.append(question.id)
    return built, skipped


def probabilities_for(answer: Dict[str, Any]) -> Dict[str, float]:
    raw = answer.get("probabilities") or {}
    if answer.get("type") == "score":
        return {str(int(k) + 1): float(v) for k, v in raw.items()}   # Jev counts score anchors from 0
    return {str(k): float(v) for k, v in raw.items()}


def _draw(probabilities: Dict[str, float], rng: random.Random) -> str:
    total = sum(max(v, 0.0) for v in probabilities.values())
    if total <= 0:
        return sorted(probabilities)[0]
    point, cumulative = rng.random() * total, 0.0
    for option, share in probabilities.items():
        cumulative += max(share, 0.0)
        if point < cumulative:
            return option
    return list(probabilities)[-1]


def answer_value(question: Any, probabilities: Dict[str, float], key: str) -> Any:
    rng = random.Random(key)
    if question.question_type == "likert":
        return int(_draw(probabilities, rng))
    if question.question_type == "multi_choice":
        k = max(1, min(int(getattr(question, "max_value", None) or 2), len(probabilities)))
        remaining, picks = dict(probabilities), []
        for _ in range(k):
            choice = _draw(remaining, rng)
            picks.append(choice)
            remaining.pop(choice, None)
        return picks
    return _draw(probabilities, rng)


def _respondent(persona: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field, value in persona.model_dump(exclude_none=True).items():
        if field in PERSONA_EXCLUDED or value in ("", [], None):
            continue
        out[field] = "; ".join(value) if isinstance(value, list) else value
    return out


def _stimulus(product: Any, market: Any, description: Optional[str]) -> str:
    parts = []
    for block in (product, market):
        if block is not None:
            dumped = {k: v for k, v in block.model_dump(exclude_none=True).items() if v not in ("", [], None)}
            parts.append(json.dumps(dumped, ensure_ascii=False))
    if description:
        parts.append(description)
    return "\n\n".join(parts)


def generate_jev_records(*, schemas: Any, config: Any, survey_schema: Any, persona_profiles: List[Any],
                         business_product_context: Any, market_context: Any, transport: Transport,
                         max_concurrency: int) -> Tuple[List[Any], Dict[str, Any], List[bool], Dict[str, Dict[str, Dict[str, float]]]]:
    """A Jev answer is kept; a Jev failure is missing. Nothing is ever filled in."""
    questions = list(survey_schema.questions)
    jev_questions, skipped = build_questions(questions)
    stimulus = _stimulus(business_product_context, market_context, getattr(survey_schema, "description", None))
    respondents = [(f"RESP_{i:03d}", persona_profiles[(i - 1) % len(persona_profiles)]) for i in range(1, config.sample_size + 1)]

    def ask(item: Tuple[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        _rid, persona = item
        payload = {"model": JEV_API_MODEL, "state": {"respondent": _respondent(persona), "stimulus": stimulus}, "questions": jev_questions}
        try:
            return transport(payload), None
        except JevRequestError:
            raise
        except Exception as error:  # noqa: BLE001 - one respondent failing is recorded, not fatal
            return None, f"{type(error).__name__}: {error}"

    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, len(respondents)))) as pool:
        replies = list(pool.map(ask, respondents))
    failed = sum(1 for reply, _ in replies if reply is None)
    total = len(respondents)
    if replies and failed == total:
        raise JevUnavailableError(f"Jev did not answer any respondent: {replies[0][1]}")
    if failed / total > MAX_FAILED_SHARE:
        raise JevTooManyFailuresError(f"Jev answered only {total - failed} of {total} respondents ({failed} failed). "
                                      "Nothing was filled in; please retry the run.")

    records: List[Any] = []
    probabilities_out: Dict[str, Dict[str, Dict[str, float]]] = {}
    missing_answers = 0
    for (respondent_id, persona), (reply, _error) in zip(respondents, replies):
        if reply is None:
            continue                                   # a failed respondent stays missing
        answers = reply.get("answers") or {}
        for question in questions:
            stated = probabilities_for(answers.get(question.id) or {})
            if not stated:
                missing_answers += 1                   # an unanswered question stays missing
                continue
            value = answer_value(question, stated, f"{config.run_id}:{respondent_id}:{question.id}")
            probabilities_out.setdefault(respondent_id, {})[question.id] = stated
            records.append(schemas.MockResponseRecord(respondent_id=respondent_id, model=JEV_MODEL_ID, experiment_mode=config.experiment_mode,
                                                      survey_title=config.survey_title, question_id=question.id, question_text=question.text,
                                                      question_type=question.question_type, answer=value,
                                                      segment_label=getattr(persona, "segment_label", None), run_id=config.run_id))
    completed = total - failed
    warnings = [f"{completed} of {total} live respondents completed; {failed} failed."] if failed else []
    if skipped:
        warnings.append(f"Jev answers only questions with listed options; these have no answers: {', '.join(skipped)}")
    debug = {"generation_mode": "jev_live", "model": JEV_MODEL_ID, "executions": completed, "answer_records": len(records),
             "questions_total": len(records), "request_errors": failed, "provider_error_count": 0, "malformed_json_count": 0,
             "questions_fallback_to_mock": 0, "questions_parsed_from_live": len(records), "questions_missing": missing_answers,
             "respondents_completed": completed, "respondents_failed": failed, "jev_warnings": warnings}
    return records, debug, [False] * len(records), probabilities_out
```

- [ ] **Step 4: Run the tests, then the full suite. Expected: PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/adapters/legacy_backend/jev_engine.py apps/api/tests/test_jev_engine.py
git commit -m "api: Jev engine — question mapping, seeded draws from its probabilities, retries, flagged fallbacks"
```

---

### Task 6: Wire Jev into the run, the model list and the Neo default

**Files:**
- Modify: `apps/api/src/adapters/legacy_backend/domain.py`:
  - `execute_simulation_run`: key check (around 1045–1056), records branch (around 1088), return dict (around 1186);
  - `list_model_catalog` (line 159).
- Modify: `apps/api/src/services/study_service.py` (the Neo demo bootstrap: experiment defaults near line 212 / `bootstrap_demo_study`).
- Test: `apps/api/tests/test_jev_live_run.py`.

**Interfaces:**
- Consumes: `generate_jev_records`, `http_transport`, `JEV_MODEL_ID`, `JevRequestError` (Task 5).
- Produces:
  - a run result with `generation_mode == "jev_live"` and `answer_probabilities`;
  - a catalog entry `{"id": "typesafe/jev", ...}` first in the list when the key is set.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from src.adapters.legacy_backend import jev_engine
from tests.test_studies_endpoints import _create_ready_to_run_study


def _jev_settings(app):
    from src.api.dependencies import get_settings
    base = app.dependency_overrides.get(get_settings, get_settings)()
    app.dependency_overrides[get_settings] = lambda: base.model_copy(update={"typesafe_api_key": "test-key"})


def test_live_jev_run_uses_the_engine_and_draws(client, app, monkeypatch):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    client.patch(f"/api/v1/studies/{study_id}/experiment", json={"sample_size": 3, "selected_models": ["typesafe/jev"],
                                                                 "experiment_mode": "split", "reruns_per_persona": 1})
    sent = []

    def fake_transport(api_key, url, **kw):
        assert api_key == "test-key"
        def send(payload):
            sent.append(payload)
            return {"answers": {qid: ({"type": "score", "probabilities": {"0": 0, "1": 0, "2": 1, "3": 0, "4": 0}} if q["type"] == "score"
                                      else {"type": "choice", "probabilities": {next(iter(q["criteria"])): 1.0}})
                                for qid, q in payload["questions"].items()}}
        return send

    monkeypatch.setattr(jev_engine, "http_transport", fake_transport)
    result = client.post(f"/api/v1/studies/{study_id}/simulation-runs").json()["data"]["simulation_run"]["result"]
    assert result["generation_mode"] == "jev_live" and result["models_used"] == ["typesafe/jev"]
    assert len(sent) == 3 and result["answer_probabilities"]
    assert all(r["answer"] == 3 for r in result["response_records"] if r["question_type"] == "likert" and not r["is_fallback"])
    assert "test-key" not in str(result)


def test_jev_with_another_model_is_rejected(client, app):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    client.patch(f"/api/v1/studies/{study_id}/experiment", json={"sample_size": 3, "selected_models": ["typesafe/jev", "openai/gpt-4o-mini"],
                                                                 "experiment_mode": "split", "reruns_per_persona": 1})
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 400 and "Jev runs on its own" in response.text


def test_catalog_lists_jev_first_when_configured(client, app):
    _jev_settings(app)
    models = client.get("/api/v1/models").json()["data"]["models"]
    assert models[0]["id"] == "typesafe/jev" and "fast, approximate" in models[0]["name"]
```

(Before writing these, check how the app provides settings to routes. If `src.api.dependencies.get_settings` is not the override point, use the same mechanism that `tests/test_studies_endpoints.py` uses to change settings.)

- [ ] **Step 2: Run them. Expected: FAIL.**

- [ ] **Step 3: Implement in `domain.py`**

- Add `from src.adapters.legacy_backend import jev_engine` to the imports.
- In `execute_simulation_run`, replace the `openrouter_available` check block (`with temporary_env(...)` through the `raise ProviderUnavailableApiError(...)`) with:

```python
    selected_models = list(experiment.selected_models or [])
    uses_jev = jev_engine.JEV_MODEL_ID in selected_models
    if uses_jev:
        if len(selected_models) > 1:
            raise ValidationApiError("Jev runs on its own: remove the other models or untick Jev.")
        if experiment.experiment_mode == "stability":
            raise ValidationApiError("Jev runs use split or mirror mode, not stability.")
        if not settings.typesafe_api_key:
            raise ProviderUnavailableApiError("TYPESAFE_API_KEY is required for live Jev runs.")
    else:
        with temporary_env({"OPENROUTER_API_KEY": settings.openrouter_api_key, "OPENROUTER_BASE_URL": settings.openrouter_base_url}):
            try:
                openrouter_available = bool(llm_client.openrouter_api_key_available())
            except Exception:
                openrouter_available = False
        if not openrouter_available:
            raise ProviderUnavailableApiError("OPENROUTER_API_KEY is required for live OpenRouter survey generation.")
    generation_mode = "jev_live" if uses_jev else "openrouter_live"
    answer_probabilities = None
```

  (Add `ValidationApiError` to the module's exceptions import if it is missing. Delete the old `generation_mode = "openrouter_live"` line.)

- Inside the existing `try:` that builds records, branch:

```python
        if uses_jev:
            records, generation_debug, record_is_fallback, answer_probabilities = jev_engine.generate_jev_records(
                schemas=schemas, config=config, survey_schema=survey_schema,
                persona_profiles=personas, business_product_context=business_product_context, market_context=market_context,
                transport=jev_engine.http_transport(settings.typesafe_api_key, settings.typesafe_base_url, timeout=60),
                max_concurrency=settings.simulation_max_concurrency,
            )
        else:
            with temporary_env({...unchanged...}):
                records, generation_debug, record_is_fallback = _generate_live_response_records_with_debug(...unchanged...)
        result = _run_simulation_compat(run_manager, config=config, generation_mode=generation_mode,
                                        provider_model_name=provider_model_name, records=records)
```

  (Set `provider_model_name = jev_engine.JEV_MODEL_ID if uses_jev else <existing expression>`.)
- Warnings: wrap the existing OpenRouter-worded warning `if`s in `if not uses_jev:` and add `warnings.extend(generation_debug.get("jev_warnings", []))`.
- Return: change `return {` to `payload = {`. After the dict, add:

```python
    if answer_probabilities is not None:
        payload["answer_probabilities"] = answer_probabilities
    return payload
```

- In `list_model_catalog`, prepend the Jev entry when it is configured:

```python
JEV_CATALOG_ENTRY = {"id": "typesafe/jev", "name": "Jev — fast, approximate (answers drawn from its probabilities)",
                     "prompt_price_per_million": None, "completion_price_per_million": None}
# at each return: models = ([JEV_CATALOG_ENTRY] if settings.typesafe_api_key else []) + models
```

`study_service.py`: where the Neo preset experiment is saved during `bootstrap_demo_study`, apply

```python
def _class_default_experiment(experiment: Dict[str, Any], settings: AppSettings) -> Dict[str, Any]:
    if settings.typesafe_api_key:
        return {**experiment, "selected_models": ["typesafe/jev"], "experiment_mode": "split"}
    return experiment
```

and add a test asserting that bootstrap with the key sets `["typesafe/jev"]`.

- [ ] **Step 4: Run the full API suite. Expected: PASS** (existing OpenRouter tests untouched).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/adapters/legacy_backend/domain.py apps/api/src/services/study_service.py apps/api/tests/test_jev_live_run.py
git commit -m "api: live runs on Jev (on its own), Jev first in the model list, Jev default for the Neo study when configured"
```

---

### Task 7: Student questions — add and remove

**Files:**
- Modify: `apps/api/src/services/study_service.py` (new functions).
- Modify: `apps/api/src/schemas/study.py` (`SurveyQuestionAddRequest`).
- Modify: `apps/api/src/api/studies.py` (two endpoints).
- Test: `apps/api/tests/test_student_questions.py`.

**Interfaces:**
- Produces: `add_survey_question(session, settings, study, *, text: str, question_type: str, options: list[str]) -> dict`.
- Produces: `remove_survey_question(session, settings, study, *, question_id: str) -> dict`.
- Both return `{"survey": ..., "workflow": ...}`, the same shape as `accept_generated_survey`.
- Produces: `DEFAULT_LIKERT_ANCHORS`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import pytest

from tests.test_studies_endpoints import _create_ready_to_run_study


def _questions(client, study_id):
    return client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]["survey"]["value"]["questions"]


def test_add_likert_and_choice_questions_get_sq_ids(client):
    study_id = _create_ready_to_run_study(client)
    first = client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": "How appealing is a solar roof?", "question_type": "likert"})
    assert first.status_code == 200
    second = client.post(f"/api/v1/studies/{study_id}/survey/questions",
                         json={"text": "Which colour would you pick?", "question_type": "single_choice", "options": ["Oak", "Slate", "White"]})
    assert second.status_code == 200
    added = [q for q in _questions(client, study_id) if q["id"].startswith("SQ")]
    assert [(q["id"], q["question_type"], len(q["options"])) for q in added] == [("SQ1", "likert", 5), ("SQ2", "single_choice", 3)]


@pytest.mark.parametrize("payload, phrase", [
    ({"text": "Tell us why", "question_type": "open_text"}, "listed options"),
    ({"text": "Pick one", "question_type": "single_choice", "options": ["Only"]}, "2 to 8"),
    ({"text": "Hi", "question_type": "likert"}, "at least 5 characters"),
    ({"text": "Rate it please", "question_type": "likert", "options": ["a", "b", ""]}, "five labels"),
])
def test_invalid_questions_are_refused(client, payload, phrase):
    study_id = _create_ready_to_run_study(client)
    response = client.post(f"/api/v1/studies/{study_id}/survey/questions", json=payload)
    assert response.status_code == 400 and phrase in response.text


def test_only_student_questions_can_be_removed(client):
    study_id = _create_ready_to_run_study(client)
    client.post(f"/api/v1/studies/{study_id}/survey/questions", json={"text": "How appealing is a solar roof?", "question_type": "likert"})
    assert client.delete(f"/api/v1/studies/{study_id}/survey/questions/Q1").status_code == 400
    assert client.delete(f"/api/v1/studies/{study_id}/survey/questions/SQ1").status_code == 200
    assert not any(q["id"] == "SQ1" for q in _questions(client, study_id))
```

(Before writing these, check the exact path to the saved survey in `GET /api/v1/studies/{id}` against `serialize_study`, and adjust `_questions` if the key differs.)

- [ ] **Step 2: Run them. Expected: FAIL.**

- [ ] **Step 3: Implement**

`schemas/study.py`:

```python
class SurveyQuestionAddRequest(BaseModel):
    text: str
    question_type: str
    options: List[str] = Field(default_factory=list)
```

`study_service.py`:

```python
STUDENT_QUESTION_PREFIX = "SQ"
DEFAULT_LIKERT_ANCHORS = ["Not at all interested", "Slightly interested", "Moderately interested", "Very interested", "Extremely interested"]


def _saved_survey(session: Session, study: Study) -> StudySectionState:
    section = _get_sections(session, study)["survey"]
    if section.status != "saved" or not section.value_json:
        raise ConflictApiError("Save a survey before adding questions.")
    return section


def _persist_survey(session: Session, settings: AppSettings, study: Study, section: StudySectionState, value: Dict[str, Any]) -> Dict[str, Any]:
    validator = load_module("backend.survey.validator", settings.legacy_app_root)
    try:
        validated = validator.validate_survey_schema(value).model_dump()
    except ValueError as exc:
        raise ValidationApiError(f"Survey is not valid: {exc}") from exc
    _save_section(session, study, "survey", validated, source_asset=section.source_asset)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    study_view = serialize_study(session, study)
    return {"survey": study_view.survey.model_dump(mode="json", by_alias=True), "workflow": study_view.derived.workflow.model_dump(mode="json")}


def add_survey_question(session: Session, settings: AppSettings, study: Study, *, text: str, question_type: str, options: List[str]) -> Dict[str, Any]:
    text = " ".join((text or "").split())
    if len(text) < 5 or len(text) > 300:
        raise ValidationApiError("Question text must be at least 5 characters (and at most 300).")
    cleaned = [o.strip() for o in options or []]
    if question_type == "likert":
        if not cleaned:
            cleaned = list(DEFAULT_LIKERT_ANCHORS)
        if len(cleaned) != 5 or not all(cleaned):
            raise ValidationApiError("A 1–5 scale needs five labels, one per point.")
        question = {"text": text, "question_type": "likert", "options": cleaned, "min_value": 1, "max_value": 5, "required": True}
    elif question_type == "single_choice":
        if not 2 <= len(cleaned) <= 8 or not all(cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValidationApiError("A single-choice question needs 2 to 8 different options.")
        question = {"text": text, "question_type": "single_choice", "options": cleaned, "required": True}
    else:
        raise ValidationApiError("Jev answers only questions with listed options: use a 1–5 scale or single choice.")
    section = _saved_survey(session, study)
    value = dict(section.value_json)
    existing = [q.get("id", "") for q in value.get("questions", [])]
    numbers = [int(i[len(STUDENT_QUESTION_PREFIX):]) for i in existing if i.startswith(STUDENT_QUESTION_PREFIX) and i[len(STUDENT_QUESTION_PREFIX):].isdigit()]
    question["id"] = f"{STUDENT_QUESTION_PREFIX}{max(numbers, default=0) + 1}"
    value["questions"] = list(value.get("questions", [])) + [question]
    return _persist_survey(session, settings, study, section, value)


def remove_survey_question(session: Session, settings: AppSettings, study: Study, *, question_id: str) -> Dict[str, Any]:
    if not (question_id.startswith(STUDENT_QUESTION_PREFIX) and question_id[len(STUDENT_QUESTION_PREFIX):].isdigit()):
        raise ValidationApiError("Only questions you added (SQ1, SQ2, ...) can be removed.")
    section = _saved_survey(session, study)
    value = dict(section.value_json)
    kept = [q for q in value.get("questions", []) if q.get("id") != question_id]
    if len(kept) == len(value.get("questions", [])):
        raise NotFoundApiError(f"Question {question_id} is not in this survey.")
    value["questions"] = kept
    return _persist_survey(session, settings, study, section, value)
```

`api/studies.py`: two endpoints with the same dependency pattern as `accept_generated_survey_endpoint`:
- `POST /api/v1/studies/{study_id}/survey/questions` with body `SurveyQuestionAddRequest` → `add_survey_question(...)`;
- `DELETE /api/v1/studies/{study_id}/survey/questions/{question_id}` → `remove_survey_question(...)`.

Both return `response_envelope(request, result)`.

- [ ] **Step 4: Run the tests and the full suite. Expected: PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/services/study_service.py apps/api/src/schemas/study.py apps/api/src/api/studies.py apps/api/tests/test_student_questions.py
git commit -m "api: students add 1–5 scale or single-choice questions (SQ1, SQ2, ...) and remove only their own"
```

---

### Task 8: Web helpers and API calls

**Files:**
- Create: `apps/web/src/lib/experiment-models.ts`, `apps/web/src/lib/survey-question-form.ts`, `apps/web/src/lib/demo-run.ts`.
- Modify: `apps/web/src/lib/api.ts` (`startSimulationRun`, plus `addSurveyQuestion` and `removeSurveyQuestion`).
- Modify: `apps/web/src/lib/backend-readiness.ts` and `apps/web/src/app/api/readiness/route.ts` (pass `providers` through).
- Test: `apps/web/tests/class-app-helpers.test.ts`.

**Interfaces:**
- Produces:
  - `JEV_MODEL_ID`;
  - `toggleModel(selected, id)`;
  - `normalizeSelectedModels(selected, fallback, jevAvailable)`;
  - `validateAddedQuestion(draft): string | null` and `toAddQuestionPayload(draft)`;
  - `isStudentQuestion(id)`;
  - `describeDemoRun(result): {reason: string; message: string} | null`;
  - `liveEngineAvailable(readiness): boolean`;
  - `startSimulationRun(studyId, source = "live")`;
  - `addSurveyQuestion(studyId, payload)` and `removeSurveyQuestion(studyId, questionId)`.

- [ ] **Step 1: Write the failing tests**

```ts
import test from "node:test";
import assert from "node:assert/strict";

import { JEV_MODEL_ID, normalizeSelectedModels, toggleModel } from "../src/lib/experiment-models";
import { DEFAULT_LIKERT_ANCHORS, isStudentQuestion, toAddQuestionPayload, validateAddedQuestion } from "../src/lib/survey-question-form";
import { describeDemoRun } from "../src/lib/demo-run";
import { liveEngineAvailable, toBackendReadinessPayload } from "../src/lib/backend-readiness";

test("Jev and other models are mutually exclusive", () => {
  assert.deepEqual(toggleModel(["openai/gpt-4o-mini"], JEV_MODEL_ID), [JEV_MODEL_ID]);
  assert.deepEqual(toggleModel([JEV_MODEL_ID], "openai/gpt-4o-mini"), ["openai/gpt-4o-mini"]);
  assert.deepEqual(toggleModel([JEV_MODEL_ID], JEV_MODEL_ID), []);
});

test("Jev alone survives normalization; otherwise two models are required", () => {
  assert.deepEqual(normalizeSelectedModels([JEV_MODEL_ID], ["a", "b"], true), [JEV_MODEL_ID]);
  assert.deepEqual(normalizeSelectedModels([], ["a", "b"], true), [JEV_MODEL_ID]);
  assert.deepEqual(normalizeSelectedModels([], ["a", "b"], false), ["a", "b"]);
  assert.deepEqual(normalizeSelectedModels(["x", JEV_MODEL_ID, "y"], ["a", "b"], true), ["x", "y"]);
});

test("added-question validation matches the API rules", () => {
  assert.equal(validateAddedQuestion({ text: "Rate the solar roof", questionType: "likert", options: [...DEFAULT_LIKERT_ANCHORS] }), null);
  assert.match(validateAddedQuestion({ text: "Hi", questionType: "likert", options: [...DEFAULT_LIKERT_ANCHORS] }) ?? "", /5 characters/);
  assert.match(validateAddedQuestion({ text: "Pick a colour", questionType: "single_choice", options: ["Oak"] }) ?? "", /2 to 8/);
  assert.deepEqual(toAddQuestionPayload({ text: " Pick  a colour ", questionType: "single_choice", options: [" Oak", "Slate ", ""] }),
    { text: "Pick a colour", question_type: "single_choice", options: ["Oak", "Slate"] });
  assert.equal(isStudentQuestion("SQ3"), true);
  assert.equal(isStudentQuestion("Q1"), false);
});

test("demo runs are described, live runs are not", () => {
  assert.equal(describeDemoRun({ generation_mode: "jev_live", warnings: [] }), null);
  const demo = describeDemoRun({ generation_mode: "demo_preloaded", warnings: ["Preloaded demo: ...", "No AI key is configured ..."], demo: { reason: "no_key" } });
  assert.equal(demo?.reason, "no_key");
  assert.match(demo?.message ?? "", /No AI key/);
});

test("readiness passes providers through", () => {
  const ready = toBackendReadinessPayload(200, { data: { status: "degraded", providers: { jev: true, openrouter: false } } });
  assert.deepEqual(ready.providers, { jev: true, openrouter: false });
  assert.equal(liveEngineAvailable(ready), true);
  assert.equal(liveEngineAvailable(toBackendReadinessPayload(200, { data: { status: "ok" } })), false);
});
```

- [ ] **Step 2: Run them. Expected: FAIL.**

`npm --prefix apps/web run test:unit`

- [ ] **Step 3: Implement**

`src/lib/experiment-models.ts`:

```ts
export const JEV_MODEL_ID = "typesafe/jev";
export const JEV_MODEL_LABEL = "Jev — fast, approximate (answers drawn from its probabilities)";

export function toggleModel(selected: string[], modelId: string): string[] {
  if (modelId === JEV_MODEL_ID) return selected.includes(JEV_MODEL_ID) ? [] : [JEV_MODEL_ID];
  const others = selected.filter((id) => id !== JEV_MODEL_ID);
  return others.includes(modelId) ? others.filter((id) => id !== modelId) : [...others, modelId];
}

export function normalizeSelectedModels(selected: string[], fallback: string[], jevAvailable: boolean): string[] {
  if (selected.length === 1 && selected[0] === JEV_MODEL_ID) return selected;
  const others = selected.filter((id) => id !== JEV_MODEL_ID);
  if (others.length >= 2) return others;
  return jevAvailable ? [JEV_MODEL_ID] : fallback;
}
```

`src/lib/survey-question-form.ts`:

```ts
export type AddedQuestionType = "likert" | "single_choice";
export type AddedQuestionDraft = { text: string; questionType: AddedQuestionType; options: string[] };
export const DEFAULT_LIKERT_ANCHORS = ["Not at all interested", "Slightly interested", "Moderately interested", "Very interested", "Extremely interested"];

const squash = (text: string) => text.split(/\s+/).filter(Boolean).join(" ");

export function toAddQuestionPayload(draft: AddedQuestionDraft) {
  return { text: squash(draft.text), question_type: draft.questionType, options: draft.options.map((o) => o.trim()).filter(Boolean) };
}

export function validateAddedQuestion(draft: AddedQuestionDraft): string | null {
  const payload = toAddQuestionPayload(draft);
  if (payload.text.length < 5 || payload.text.length > 300) return "Question text must be at least 5 characters (and at most 300).";
  if (draft.questionType === "likert" && payload.options.length !== 5) return "A 1–5 scale needs five labels, one per point.";
  if (draft.questionType === "single_choice") {
    const unique = new Set(payload.options);
    if (payload.options.length < 2 || payload.options.length > 8 || unique.size !== payload.options.length) {
      return "A single-choice question needs 2 to 8 different options.";
    }
  }
  return null;
}

export const isStudentQuestion = (id: string) => /^SQ\d+$/.test(id);
```

`src/lib/demo-run.ts`:

```ts
type RunLike = { generation_mode?: string | null; warnings?: string[] | null; demo?: { reason?: string } | null };

export function describeDemoRun(result: RunLike | null | undefined): { reason: string; message: string } | null {
  if (!result || result.generation_mode !== "demo_preloaded") return null;
  const warnings = result.warnings ?? [];
  return { reason: result.demo?.reason ?? "requested", message: [warnings[0], warnings[1]].filter(Boolean).join(" ") };
}
```

`src/lib/backend-readiness.ts`:
- Add `providers?: { jev: boolean; openrouter: boolean }` to `BackendReadinessPayload`.
- Extend `HealthEnvelope.data` with `providers?: { jev?: boolean; openrouter?: boolean }`.
- In each returned object, include the line below, built once at the top of the function:

```ts
  const rawProviders = typeof payload === "object" && payload !== null ? (payload as HealthEnvelope).data?.providers : undefined;
  const providers = rawProviders ? { jev: Boolean(rawProviders.jev), openrouter: Boolean(rawProviders.openrouter) } : undefined;
```

- Add:

```ts
export function liveEngineAvailable(readiness: BackendReadinessPayload | null | undefined): boolean {
  return Boolean(readiness?.providers && (readiness.providers.jev || readiness.providers.openrouter));
}
```

`src/app/api/readiness/route.ts`: no change needed if it returns `toBackendReadinessPayload(...)` as is (it does: line 39).

`src/lib/api.ts`:

```ts
export async function startSimulationRun(studyId: string, source: "live" | "demo" = "live") {
  const apiBaseUrl = getApiBaseUrl();
  const response = await fetch(`${apiBaseUrl}/api/v1/studies/${studyId}/simulation-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });
  // ...rest unchanged
}

export async function addSurveyQuestion(studyId: string, payload: { text: string; question_type: string; options: string[] }) {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/studies/${studyId}/survey/questions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readApiErrorMessage(response, `Adding the question failed (${response.status})`));
  return (await response.json()).data;
}

export async function removeSurveyQuestion(studyId: string, questionId: string) {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/studies/${studyId}/survey/questions/${encodeURIComponent(questionId)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiErrorMessage(response, `Removing the question failed (${response.status})`));
  return (await response.json()).data;
}
```

(If other calls in `api.ts` add auth headers through a helper, use the same helper here.)

- [ ] **Step 4: Run `test:unit` and `build`. Expected: PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib apps/web/src/app/api/readiness/route.ts apps/web/tests/class-app-helpers.test.ts
git commit -m "web: helpers for Jev selection, added questions, demo runs and provider readiness; API calls for them"
```

---

### Task 9: Web components

**Files:**
- Modify: `apps/web/src/components/sections/run-simulation-section.tsx` (`handleRunStudy` at line 208, button at line 307).
- Modify: `apps/web/src/components/sections/experiment-section.tsx` (`DEFAULT_MODEL_OPTIONS` at line 40, normalization at line 932, model toggle handler).
- Modify: `apps/web/src/components/sections/survey-section.tsx` (render the card).
- Create: `apps/web/src/components/sections/add-question-card.tsx`.

**Interfaces:**
- Consumes: everything produced in Task 8.

- [ ] **Step 1: Run step.**
  - Change `handleRunStudy()` to `handleRunStudy(source: "live" | "demo" = "live")` and pass `source` to `startSimulationRun(resolvedStudyId, source)`.
  - Add `const [readiness, setReadiness] = useState<BackendReadinessPayload | null>(null);` and a mount effect: `fetch("/api/readiness").then((r) => r.json()).then(setReadiness).catch(() => setReadiness(null));`.
  - Replace the single button at line 307 with:

```tsx
<Button onClick={() => handleRunStudy("live")} disabled={isRunning || !liveEngineAvailable(readiness)}>
  Run live{readiness?.providers?.jev ? " (Jev)" : ""}
</Button>
<Button variant="secondary" onClick={() => handleRunStudy("demo")} disabled={isRunning}>
  Show preloaded demo (no AI)
</Button>
{!liveEngineAvailable(readiness) ? (
  <p className="text-sm text-white/60">No AI key on this server — use the preloaded demo.</p>
) : null}
```

  (Use the `Button` variants that exist in `@/components/ui/button`.)

  - Above the results summary, add the banner. It is red and bold when Jev was down, so preloaded answers are never mistaken for a live run:

```tsx
{describeDemoRun(latestRun?.result) ? (
  <div role="status" className={describeDemoRun(latestRun?.result)?.reason === "jev_unavailable"
      ? "rounded-xl border-2 border-red-400 bg-red-500/15 p-4 text-base font-semibold"
      : "rounded-xl border border-amber-300/40 bg-amber-300/10 p-3 text-sm"}>
    {describeDemoRun(latestRun?.result)?.message}
  </div>
) : null}
```

  - In `handleRunStudy`'s `catch`, the error message from the 503 ("Jev is temporarily unavailable. Your new question requires a live run…" or "Jev answered only N of M…") already reaches `setStatus`.
    - Keep both buttons enabled after an error, so "Run live" is the retry and "Show preloaded demo (no AI)" is the way to the original survey's demo.
    - When the message contains "requires a live run", add the line: "Your added questions are not in the preloaded demo."

- [ ] **Step 2: Experiment step.**
  - Add `{ id: JEV_MODEL_ID, name: JEV_MODEL_LABEL }` as the first entry of `DEFAULT_MODEL_OPTIONS`.
  - At line 932 replace the `>= 2 ? … : DEFAULT_SELECTED_MODEL_IDS` expression with `normalizeSelectedModels(selectedModels, DEFAULT_SELECTED_MODEL_IDS, jevAvailable)`, where `jevAvailable` is passed into `experimentPayloadToDraft` from the loaded catalog (`availableModels.some((m) => m.id === JEV_MODEL_ID)`; `false` before the catalog loads).
  - In the handler that adds or removes a model from `draft.selected_models`, use `toggleModel(draft.selected_models, model.id)`.
  - When Jev is selected, show "Jev runs on its own".

- [ ] **Step 3: Survey step.** Create `add-question-card.tsx`:

```tsx
"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { addSurveyQuestion, removeSurveyQuestion } from "@/lib/api";
import { DEFAULT_LIKERT_ANCHORS, isStudentQuestion, toAddQuestionPayload, validateAddedQuestion, type AddedQuestionType } from "@/lib/survey-question-form";

type Question = { id: string; text: string; question_type: string };

export function AddQuestionCard({ studyId, questions, onChanged }: { studyId: string; questions: Question[]; onChanged: () => Promise<void> | void }) {
  const [text, setText] = useState("");
  const [questionType, setQuestionType] = useState<AddedQuestionType>("likert");
  const [options, setOptions] = useState<string[]>([...DEFAULT_LIKERT_ANCHORS]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const added = questions.filter((q) => isStudentQuestion(q.id));

  function switchType(next: AddedQuestionType) {
    setQuestionType(next);
    setOptions(next === "likert" ? [...DEFAULT_LIKERT_ANCHORS] : ["", ""]);
  }

  async function submit() {
    const draft = { text, questionType, options };
    const problem = validateAddedQuestion(draft);
    if (problem) return setMessage(problem);
    setBusy(true);
    try {
      await addSurveyQuestion(studyId, toAddQuestionPayload(draft));
      setText("");
      switchType(questionType);
      setMessage("Added. Run live to get answers to it.");
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add the question.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await removeSurveyQuestion(studyId, id);
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <GlassPanel className="space-y-3 p-5">
      <h3 className="text-lg font-semibold">Add your own question</h3>
      <p className="text-sm text-white/60">Jev answers questions with listed options: a 1–5 scale or a single choice.</p>
      <textarea className="w-full rounded-lg bg-white/5 p-2" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Question text" />
      <div className="flex gap-2">
        <Button variant={questionType === "likert" ? "primary" : "secondary"} onClick={() => switchType("likert")}>1–5 scale</Button>
        <Button variant={questionType === "single_choice" ? "primary" : "secondary"} onClick={() => switchType("single_choice")}>Single choice</Button>
      </div>
      {options.map((option, index) => (
        <input key={index} className="w-full rounded-lg bg-white/5 p-2" value={option}
          placeholder={questionType === "likert" ? `Label for ${index + 1}` : `Option ${index + 1}`}
          onChange={(e) => setOptions(options.map((o, i) => (i === index ? e.target.value : o)))} />
      ))}
      {questionType === "single_choice" && options.length < 8 ? (
        <Button variant="secondary" onClick={() => setOptions([...options, ""])}>Add option</Button>
      ) : null}
      <Button onClick={submit} disabled={busy}>Add question</Button>
      {message ? <p role="status" className="text-sm">{message}</p> : null}
      {added.length ? (
        <ul className="space-y-1 text-sm">
          {added.map((q) => (
            <li key={q.id} className="flex items-center justify-between gap-2">
              <span>{q.id}: {q.text}</span>
              <Button variant="secondary" onClick={() => remove(q.id)} disabled={busy}>Remove</Button>
            </li>
          ))}
        </ul>
      ) : null}
    </GlassPanel>
  );
}
```

  In `survey-section.tsx`, render `<AddQuestionCard studyId={studyId} questions={study?.survey?.value?.questions ?? []} onChanged={() => refreshStudy(studyId)} />` below the saved-survey summary, only when a survey is saved. Use the same `studyId`, `study` and `refreshStudy` names the section already reads from `useStudy()`, and the `Button` variant names that exist.

- [ ] **Step 4: Build and test. Expected: PASS.**

`npm --prefix apps/web run build && npm --prefix apps/web run test:unit`

- [ ] **Step 5: Local click-through.**
  - Start the API with no keys, plus the web app.
  - Neo demo study → load survey → "Show preloaded demo (no AI)".
  - Results, analysis and insights render with the amber banner.
  - Add SQ1 → a demo run warns "Run live to answer these: SQ1".

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/sections
git commit -m "web: run live or show the preloaded demo, Jev in the model list, add-your-own-question card"
```

---

### Task 10: Verification, hand-off, PR

- [ ] **Step 1: Full checks.**

```bash
cd apps/api && .venv/bin/python -m pytest -q && cd ../.. \
  && npm --prefix apps/web run build && npm --prefix apps/web run test:unit
git grep -nE "TYPESAFE_API_KEY=.+|sk-or-|aytm_[0-9]" -- . ':!docs' ; echo "grep exit $? (1 = clean)"
```

- [ ] **Step 2: Re-read the fixture.**
  - `python -c "import gzip,json;d=json.loads(gzip.decompress(open('apps/api/src/services/demo_survey_fixture.json.gz','rb').read()));print(d['source'], len(d['respondents']))"`
  - Expected: the R021 source and 100 respondents.

- [ ] **Step 3 (paid, about 1¢, only after Minh says OK): one live Jev check.**
  - Put `TYPESAFE_API_KEY` in local `apps/api/.env` (Minh does this; never echo it).
  - Run the Neo study with sample size 5 plus SQ1.
  - Expected: `generation_mode` is `jev_live`, no fallbacks, and SQ1 answered.

- [ ] **Step 4: Push and open the PR into `main`.**
  - PR body (no AI footer):
    - what changed;
    - the env var `TYPESAFE_API_KEY` for Render;
    - the readiness fields for Anderson's pages;
    - the test list;
    - "demo works with no key".
  - Then `get_status` / `bind_pr` with the ccd_pr tools.

- [ ] **Step 5: Text Anderson.**
  - The readiness fields `providers` and `demo_available`.
  - The banner wording.
  - The PR link.
  - The request: add `TYPESAFE_API_KEY` on Render, merge, deploy Tuesday night.

- [ ] **Step 6: Wednesday-morning smoke test on the deployed site:**
  - the preloaded demo;
  - a 30-persona Jev run;
  - an added question answered live;
  - Run live disabled when the key is absent (checked locally).

---

## Self-review (done)

- **Spec coverage:**

  | Spec | Tasks |
  | --- | --- |
  | Routing | 4, 6 |
  | Demo data | 2, 3 |
  | Jev engine | 5, 6 |
  | Frontend + editing | 7, 8, 9 |
  | Readiness | 1, 8 |
  | Testing and deploy | 10 |

- **Placeholder scan:** none. Three spots tell the implementer to match an existing helper or field name they must read first: the `get_settings` override, the saved-survey JSON path, and `Button` variants. Each names the file to check.
- **Type consistency:**
  - `build_demo_run_result`, `JevUnavailableError`, `JEV_MODEL_ID`, `generate_jev_records`, `toggleModel`, `normalizeSelectedModels`, `describeDemoRun` and `liveEngineAvailable` are used with the same signatures throughout.
  - Validation errors are 400 everywhere (`ValidationApiError`). Spec section 1's "422" is corrected to 400 to match the app.
