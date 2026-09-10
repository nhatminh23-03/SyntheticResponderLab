"""Offline tests for the phase 2 survey runner. No network: OpenRouter is stubbed.

Run from the repository root:
    apps/api/.venv/bin/python -m pytest research/neo_persona_set/phase2 -q
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_survey  # noqa: E402

HEADER = [
    "persona_id", "age_bucket", "income_bucket", "ownership", "work_mode", "home_type", "lifestyle_tags",
    "fit_tier", "awareness_stage", "segment_label", "likely_use_case", "likely_barrier", "affordability_pressure",
    "exact_age", "exact_household_income", "sex", "county", "marital_status", "education", "occupation",
    "employment_status", "hours_worked_per_week", "commute_mode", "commute_minutes", "household_size",
    "children_in_household", "household_type", "tenure_detail", "bedrooms", "rooms", "year_built", "moved_in",
    "vehicles", "housing_cost_pct_of_income", "name", "story_headline", "story_biography", "story_priorities",
]


def _row(pid: str, age: int, income: int) -> dict:
    return {
        "persona_id": pid, "age_bucket": "30-34", "income_bucket": "$100k-$150k", "ownership": "owner",
        "work_mode": "commutes", "home_type": "detached single-family", "lifestyle_tags": "has kids;married",
        "fit_tier": "", "awareness_stage": "", "segment_label": "", "likely_use_case": "", "likely_barrier": "",
        "affordability_pressure": "", "exact_age": str(age), "exact_household_income": str(income), "sex": "Female",
        "county": "Kern", "marital_status": "Married", "education": "high school diploma", "occupation": "Tutors",
        "employment_status": "Not in labor force", "hours_worked_per_week": "", "commute_mode": "", "commute_minutes": "",
        "household_size": "4", "children_in_household": "2", "household_type": "Married couple household",
        "tenure_detail": "Owned with mortgage or loan", "bedrooms": "3", "rooms": "5", "year_built": "1980 to 1989",
        "moved_in": "10 to 19 years", "vehicles": "2 vehicles", "housing_cost_pct_of_income": "17", "name": "Janet Kaur",
        "story_headline": "Stay-at-home parent in Kern County", "story_biography": "Janet grew up in the Central Valley.",
        "story_priorities": "Build emergency fund; Complete driveway resealing",
    }


@pytest.fixture
def persona_csv(tmp_path: Path) -> Path:
    path = tmp_path / "personas.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerow(_row("P001", 32, 100547))
        writer.writerow(_row("P002", 45, 230000))
        writer.writerow(_row("P003", 61, 115738))
    return path


@pytest.fixture(scope="module")
def survey():
    return run_survey.load_survey(run_survey.DEFAULT_SURVEY)


# --- loading ----------------------------------------------------------------------------------


def test_load_personas_maps_blanks_ints_and_story(persona_csv: Path) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    assert [p.persona_id for p in personas] == ["P001", "P002", "P003"]
    first = personas[0]
    assert first.fit_tier is None and first.awareness_stage is None and first.segment_label is None
    assert first.lifestyle_tags == ["has kids", "married"]
    assert first.census_record["exact_age"] == 32
    assert first.census_record["exact_household_income"] == 100547
    assert "hours_worked_per_week" not in first.census_record  # blank stays out
    assert first.story["headline"].startswith("Stay-at-home")
    assert first.story["priorities"] == ["Build emergency fund", "Complete driveway resealing"]
    dumped = first.model_dump()
    assert "fit_tier" not in dumped and "segment_label" not in dumped
    assert dumped["census_record"]["exact_age"] == 32 and dumped["story"]["headline"]


def test_prompt_variants_drop_story_and_census(persona_csv: Path) -> None:
    census_only = run_survey.load_personas(persona_csv, limit=1, prompt_variant="census")[0]
    assert census_only.census_record and census_only.story is None
    buckets = run_survey.load_personas(persona_csv, limit=1, prompt_variant="buckets")[0]
    assert buckets.census_record is None and buckets.story is None and buckets.name is None
    assert set(buckets.model_dump()) == {"persona_id", "age_bucket", "income_bucket", "ownership", "home_type", "work_mode", "lifestyle_tags"}


def test_limit_and_duplicate_ids(persona_csv: Path, tmp_path: Path) -> None:
    assert len(run_survey.load_personas(persona_csv, limit=2, prompt_variant="full")) == 2
    dup = tmp_path / "dup.csv"
    with open(dup, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerow(_row("P001", 32, 100547))
        writer.writerow(_row("P001", 40, 120000))
    with pytest.raises(ValueError, match="duplicate"):
        run_survey.load_personas(dup, limit=None, prompt_variant="full")


def test_survey_loads_39_items(survey) -> None:
    ids = [q.id for q in survey.questions]
    assert len(ids) == 39
    assert ids[:6] == ["S3", "Q0A", "Q0B", "Q1", "Q2", "Q3"]
    assert "Q5_1" in ids and "Q5_7" in ids and ids[-1] == "Q30"


# --- guards -----------------------------------------------------------------------------------


def test_path_fence_rejects_real_data(tmp_path: Path) -> None:
    for bad in ("raw 600-participant dataset and a sample report from aytm/x.csv", "survey-760085-2026-03-25-raw-data.csv", "AYTM/report.pdf"):
        with pytest.raises(SystemExit) as excinfo:
            run_survey.assert_not_real_data(tmp_path / bad, "--personas")
        assert excinfo.value.code == 3
    assert run_survey.assert_not_real_data(tmp_path / "600_persona" / "phase1.csv", "--personas")


def test_persona_header_fence_rejects_survey_columns(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        run_survey.assert_persona_header_is_synthetic(["Response ID", "Q1: Please read", "Gender"], tmp_path / "x.csv")
    run_survey.assert_persona_header_is_synthetic(HEADER, tmp_path / "ok.csv")


# --- shims ------------------------------------------------------------------------------------


def _likert_question(options):
    return run_survey.schemas.SurveyQuestion(id="QX", text="How interested?", question_type="likert", options=options, min_value=1, max_value=5)


def test_likert_label_mapping_counts_and_can_be_disabled() -> None:
    options = ["Not at all interested", "Slightly interested", "Moderately interested", "Very interested", "Extremely interested"]
    question = _likert_question(options)
    manager = run_survey.CoercingRunManager(run_survey.run_manager)
    assert manager._coerce_openrouter_answer_value(question, 4) == 4
    assert manager._coerce_openrouter_answer_value(question, "Very interested") == 4
    assert manager._coerce_openrouter_answer_value(question, "very interested.") == 4
    assert manager.likert_labels_mapped == 2
    assert manager._coerce_openrouter_answer_value(question, "interested") is None  # ambiguous stays fallback
    disabled = run_survey.CoercingRunManager(run_survey.run_manager, enabled=False)
    assert disabled._coerce_openrouter_answer_value(question, "Very interested") is None
    assert manager._extract_answer_map_from_openrouter_result({"ok": True, "parsed_json": {"answers": {"Q1": 3}}}) == {"Q1": 3}


def test_prompt_builder_shim_sets_budget_and_tag(survey, persona_csv: Path) -> None:
    persona = run_survey.load_personas(persona_csv, limit=1, prompt_variant="full")[0]
    product, market = run_survey.load_contexts()
    builder = run_survey.TaggingPromptBuilder(run_survey.prompt_builder, max_tokens=4000, temperature=0.2)
    payload = builder.build_openrouter_prompt_payload(persona=persona, survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None)
    assert payload["max_tokens"] == 4000 and payload["temperature"] == 0.2 and payload["_persona_id"] == "P001"
    user = payload["messages"][1]["content"]
    assert '"exact_age": 32' in user and "Stay-at-home parent" in user and '"fit_tier"' not in user
    assert "Tahoe Mini" in user


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _ok_payload(content: str, finish_reason: str = "stop"):
    return {
        "id": "gen-1", "model": "deepseek/deepseek-v4-pro-0813", "provider": "DeepInfra",
        "choices": [{"finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 6000, "completion_tokens": 900, "total_tokens": 6900, "cost": 0.0058},
    }


def _client(**overrides):
    kwargs = dict(api_key="k", base_url="https://example.invalid/api/v1", seed=123, max_retries=3, retry_base_seconds=0.0, progress_every=1000)
    kwargs.update(overrides)
    return run_survey.OpenRouterClient(**kwargs)


def test_client_body_retries_transient_and_captures_usage(monkeypatch) -> None:
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return _FakeResponse(429, {"error": {"code": 429, "message": "rate limited"}})
        return _FakeResponse(200, _ok_payload('{"answers": {"Q1": 3}}'))

    monkeypatch.setattr(run_survey.requests, "post", fake_post)
    client = _client(provider_order=["together", "fireworks"], provider_ignore=["DigitalOcean"], allow_provider_fallbacks=False, reasoning_effort="off")
    result = client.generate_survey_response_with_openrouter(
        model_name="deepseek/deepseek-v4-pro-0813", prompt_payload={"messages": [{"role": "user", "content": "x"}], "max_tokens": 4000, "temperature": 0.2, "_persona_id": "P001"}, timeout=5
    )
    assert result["ok"] and result["parsed_json"] == {"answers": {"Q1": 3}}
    body = calls[-1]
    assert body["seed"] == 123 and body["usage"] == {"include": True} and body["max_tokens"] == 4000
    assert body["provider"] == {"order": ["together", "fireworks"], "allow_fallbacks": False, "ignore": ["DigitalOcean"]}
    assert body["reasoning"] == {"enabled": False}
    assert "provider" not in _client().build_body("m", {"messages": []})
    assert "reasoning" not in _client(reasoning_effort="default").build_body("m", {"messages": []})
    assert "_persona_id" not in body
    capture = client.captures["P001"]
    assert capture["attempts"] == 2 and capture["provider"] == "DeepInfra" and capture["usage"]["prompt_tokens"] == 6000
    assert client.stats["retries"] == 1 and client.stats["prompt_tokens"] == 6000
    assert abs(client.usd_reported - 0.0058) < 1e-6


def test_client_returns_terminal_status_without_retry(monkeypatch) -> None:
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _FakeResponse(402, text='{"error": {"message": "requires more credits"}}')

    monkeypatch.setattr(run_survey.requests, "post", fake_post)
    client = _client()
    result = client.generate_survey_response_with_openrouter(model_name="m", prompt_payload={"messages": [], "_persona_id": "P009"}, timeout=5)
    assert result["ok"] is False and result["status_code"] == 402 and len(calls) == 1
    assert run_survey.domain._terminal_provider_error(result, "m") is not None


def test_client_recovers_fenced_json_and_retries_truncation(monkeypatch) -> None:
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            return _FakeResponse(200, _ok_payload('{"answers": {"Q1": 3, "Q2"', finish_reason="length"))
        return _FakeResponse(200, _ok_payload('Sure! ```json\n{"answers": {"Q1": 3}}\n```'))

    monkeypatch.setattr(run_survey.requests, "post", fake_post)
    client = _client()
    result = client.generate_survey_response_with_openrouter(model_name="m", prompt_payload={"messages": [], "_persona_id": "P002"}, timeout=5)
    assert result["ok"] and result["parsed_json"] == {"answers": {"Q1": 3}}
    assert client.captures["P002"]["json_recovered"] is True and client.stats["finish_length"] == 1


# --- end to end with a stub client ------------------------------------------------------------


class StubClient:
    """Answers every question validly; records nothing over the network."""

    def __init__(self, survey) -> None:
        self.survey = survey
        self.captures = {}
        self.stats = Counter()
        self.usd_reported = 0.0

    def generate_survey_response_with_openrouter(self, *, model_name, prompt_payload, timeout=0):
        pid = prompt_payload.get("_persona_id")
        answers = {}
        for q in self.survey.questions:
            if q.question_type == "single_choice":
                answers[q.id] = "Moderately interested" if q.id == "Q30" else q.options[0]
            elif q.question_type == "multi_choice":
                answers[q.id] = [q.options[0], q.options[1]]
            elif q.question_type == "likert":
                answers[q.id] = 3
            else:
                answers[q.id] = "n/a"
        raw = json.dumps({"answers": answers})
        self.captures[pid] = {"persona_id": pid, "model_served": model_name, "provider": "stub", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": None}, "raw_text": raw, "parsed_ok": True, "finish_reason": "stop"}
        self.stats["calls"] += 1
        self.stats["prompt_tokens"] += 10
        self.stats["completion_tokens"] += 5
        return {"ok": True, "parsed_json": json.loads(raw), "raw_text": raw, "error": None, "status_code": 200}


def _args(tmp_path: Path, persona_csv: Path, **overrides) -> argparse.Namespace:
    values = dict(
        personas=persona_csv, survey=run_survey.DEFAULT_SURVEY, out_dir=tmp_path / "runs", limit=None, run_tag=None,
        max_tokens=4000, temperature=0.2, timeout=5, max_retries=0, concurrency=2, prompt_variant="full",
        provider_order=None, provider_ignore=["DigitalOcean"], no_provider_fallbacks=False, json_mode=False, reasoning_effort="off",
        no_likert_label_map=False, fallback_threshold=0.01, price_in=None, price_out=None, progress_every=1000,
        repair_rounds=2, max_failed_respondent_share=0.005,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def test_end_to_end_with_stub_client(tmp_path: Path, persona_csv: Path, survey) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(
        model="stub/model", repeat=1, seed=202609091, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
        args=args, client=StubClient(survey), census_lookup=run_survey.persona_census_lookup(persona_csv),
    )
    assert manifest["status"] == "completed", manifest["guardrails"]
    run_dir = Path(manifest["run_dir"])
    names = {p.name for p in run_dir.iterdir()}
    assert {"answers_long.csv", "answers_wide.csv", "questions.csv", "raw_responses.jsonl", "generation_debug.json", "prompt_sample.txt", "manifest.json", "summary.md"} <= names

    with open(run_dir / "answers_long.csv", newline="", encoding="utf-8") as handle:
        long_rows = list(csv.DictReader(handle))
    assert len(long_rows) == 3 * 39
    assert {row["persona_id"] for row in long_rows} == {"P001", "P002", "P003"}
    assert all(row["is_fallback"] == "false" for row in long_rows)
    q20 = next(row for row in long_rows if row["question_id"] == "Q20")
    assert "|" in q20["answer"] and json.loads(q20["answer_json"]) == q20["answer"].split("|")

    with open(run_dir / "answers_wide.csv", newline="", encoding="utf-8") as handle:
        wide_rows = list(csv.DictReader(handle))
    assert len(wide_rows) == 3 and wide_rows[0]["Q30"] == "Moderately interested" and wide_rows[0]["all_live"] == "true"
    assert list(wide_rows[0].keys())[6:12] == ["S3", "Q0A", "Q0B", "Q1", "Q2", "Q3"]

    counts = manifest["counts"]
    assert counts["respondents"] == 3 and counts["answers"] == 117 and counts["fallback_answers"] == 0
    assert manifest["summary"]["Q30_attention_check"]["pass_rate"] == 1.0
    assert manifest["tokens"]["prompt"] == 30
    index = list(csv.DictReader(open(args.out_dir / "index.csv", newline="", encoding="utf-8")))
    assert len(index) == 1 and index[0]["status"] == "completed" and index[0]["run_id"] == manifest["run_id"]


def test_guardrails_flag_fabricated_runs(tmp_path: Path, persona_csv: Path, survey) -> None:
    class BrokenClient(StubClient):
        def generate_survey_response_with_openrouter(self, *, model_name, prompt_payload, timeout=0):
            pid = prompt_payload.get("_persona_id")
            self.captures[pid] = {"persona_id": pid, "error": "timed out"}
            self.stats["calls"] += 1
            return {"ok": False, "parsed_json": None, "raw_text": "", "error": "OpenRouter request timed out.", "status_code": None}

    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(
        model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
        args=args, client=BrokenClient(survey), census_lookup={},
    )
    assert manifest["status"] == "failed" and manifest["run_dir"].endswith("_failed")
    assert any(reason.startswith("failed_respondents=3") for reason in manifest["guardrails"]["reasons"])
    assert manifest["counts"]["fallback_answers"] == 117
    assert manifest["repair"]["rounds_run"] == 2 and all(entry["improved"] == 0 for entry in manifest["repair"]["log"])


class FlakyClient(StubClient):
    """Returns garbage (wrong question ids) for P002 on the main batch, valid answers on repair."""

    def generate_survey_response_with_openrouter(self, *, model_name, prompt_payload, timeout=0):
        pid = prompt_payload.get("_persona_id")
        if pid == "P002" and getattr(self, "current_round", 0) == 0:
            raw = json.dumps({"answers": {"Q8": 3, "Q9": "Moderately likely"}})
            self.captures[pid] = {"persona_id": pid, "provider": "DigitalOcean", "parsed_ok": True, "raw_text": raw, "repair_round": 0, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
            self.stats["calls"] += 1
            return {"ok": True, "parsed_json": json.loads(raw), "raw_text": raw, "error": None, "status_code": 200}
        result = super().generate_survey_response_with_openrouter(model_name=model_name, prompt_payload=prompt_payload, timeout=timeout)
        self.captures[pid]["repair_round"] = getattr(self, "current_round", 0)
        return result


def test_repair_round_replaces_persona_with_fabricated_answers(tmp_path: Path, persona_csv: Path, survey) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv)
    args.out_dir.mkdir(parents=True)
    client = FlakyClient(survey)
    manifest = run_survey.run_one(
        model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
        args=args, client=client, census_lookup={},
    )
    assert manifest["status"] == "completed", manifest["guardrails"]
    assert manifest["counts"]["fallback_answers"] == 0 and manifest["counts"]["request_errors"] == 0
    assert manifest["repair"]["rounds_run"] == 1
    assert manifest["repair"]["log"][0] == {"round": 1, "personas": 1, "improved": 1, "persona_ids": ["P002"]}
    assert client.captures["P002"]["repair_round"] == 1
    with open(Path(manifest["run_dir"]) / "answers_long.csv", newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["persona_id"] == "P002"]
    assert len(rows) == 39 and all(row["is_fallback"] == "false" for row in rows) and rows[0]["respondent_id"] == "RESP_002"
    assert manifest["diagnostics"]["fallback_by_question"] == {}


def test_dash_and_question_id_normalization() -> None:
    manager = run_survey.CoercingRunManager(run_survey.run_manager, question_ids=["Q21", "Q22", "Q20"])
    remapped = manager._extract_answer_map_from_openrouter_result({"ok": True, "parsed_json": {"answers": {"q21": "55-64", " Q22 ": "x", "Q99": 1}}})
    assert remapped == {"Q21": "55-64", "Q22": "x", "Q99": 1} and manager.ids_remapped == 1  # the engine already trims " Q22 "
    age = run_survey.schemas.SurveyQuestion(id="Q21", text="Age", question_type="single_choice", options=["45–54", "55–64", "65 or older"])
    assert manager._coerce_openrouter_answer_value(age, "55-64") == "55–64"
    assert manager._coerce_openrouter_answer_value(age, "55–64") == "55–64"
    assert manager._coerce_openrouter_answer_value(age, "twenties") is None
    multi = run_survey.schemas.SurveyQuestion(id="Q20", text="Channels", question_type="multi_choice", options=["Google / Search ads", "Friend / family referral"])
    assert manager._coerce_openrouter_answer_value(multi, ["google / search ads", "made up"]) == ["Google / Search ads"]
    assert manager.dashes_normalized == 1  # the multi-choice case is matched by the engine itself, case-insensitively


def test_bucket_matching_for_consistency_checks() -> None:
    age_options = ["18–24", "25–34", "35–44", "45–54", "55–64", "65 or older"]
    assert run_survey.bucket_for(32, age_options) == "25–34"
    assert run_survey.bucket_for(70, age_options) == "65 or older"
    income_options = ["Less than $50,000", "$50,000–$99,999", "$100,000–$149,999", "$150,000–$199,999", "$200,000 or more"]
    assert run_survey.bucket_for(104999, income_options) == "$100,000–$149,999"
    assert run_survey.bucket_for(40000, income_options) == "Less than $50,000"
    assert run_survey.bucket_for(250000, income_options) == "$200,000 or more"
