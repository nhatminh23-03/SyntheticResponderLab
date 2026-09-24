"""Offline tests for the phase 2 survey runner. No network: OpenRouter is stubbed.

Run from the repository root:
    apps/api/.venv/bin/python -m pytest research/neo_persona_set/phase2 -q
"""

from __future__ import annotations

import argparse
import csv
import json
import types
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


def test_bucket_labels_are_derived_from_exact_values(tmp_path: Path) -> None:
    """The matched draw carries labels from the screened pool ("$100k-$150k" on a $31,980 income)."""
    path = tmp_path / "matched.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        row = _row("P001", 24, 31980)
        row["age_bucket"] = "30-34"
        row["income_bucket"] = "$100k-$150k"
        writer.writerow(row)
        row = _row("P002", 67, 214092)
        row["age_bucket"] = "65"
        row["income_bucket"] = "$200k-$300k"
        writer.writerow(row)
    personas = run_survey.load_personas(path, limit=None, prompt_variant="full")
    assert (personas[0].age_bucket, personas[0].income_bucket) == ("18-24", "$25k-$50k")
    assert (personas[1].age_bucket, personas[1].income_bucket) == ("65+", "$200k-$300k")
    assert run_survey.LAST_LOAD_STATS == {"age_bucket_recomputed": 2, "income_bucket_recomputed": 1}
    kept = run_survey.load_personas(path, limit=None, prompt_variant="full", recompute_buckets=False)
    assert (kept[0].age_bucket, kept[0].income_bucket) == ("30-34", "$100k-$150k")
    assert run_survey.LAST_LOAD_STATS == {"age_bucket_recomputed": 0, "income_bucket_recomputed": 0}


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

    def __init__(self, survey, reasons: bool = False) -> None:
        self.survey = survey
        self.reasons = reasons
        self.captures = {}
        self.current_chunk = None
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
        if self.reasons:
            raw = json.dumps({"answers": [{"question_id": qid, "answer": value, "reason": f"because {qid}"} for qid, value in answers.items()]})
        else:
            raw = json.dumps({"answers": answers})
        key = pid if self.current_chunk is None else f"{pid}#c{self.current_chunk}"
        self.captures[key] = {"persona_id": pid, "model_served": model_name, "provider": "stub", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": None}, "raw_text": raw, "parsed_ok": True, "finish_reason": "stop"}
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
        repair_rounds=2, max_failed_respondent_share=0.005, keep_file_buckets=False, survey_description="drop", persona_ids=None,
        temperature_jitter=0.0, no_sponsor_context=False, trait_mix=None, reason_per_answer=False, questions_per_call=0, interest_note=False,
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

    with open(run_dir / "answers_long.csv", newline="", encoding="utf-8-sig") as handle:
        long_rows = list(csv.DictReader(handle))
    assert len(long_rows) == 3 * 39
    assert {row["persona_id"] for row in long_rows} == {"P001", "P002", "P003"}
    assert all(row["is_fallback"] == "false" for row in long_rows)
    q20 = next(row for row in long_rows if row["question_id"] == "Q20")
    assert "|" in q20["answer"] and json.loads(q20["answer_json"]) == q20["answer"].split("|")

    with open(run_dir / "answers_wide.csv", newline="", encoding="utf-8-sig") as handle:
        wide_rows = list(csv.DictReader(handle))
    assert len(wide_rows) == 3 and wide_rows[0]["Q30"] == "Moderately interested" and wide_rows[0]["all_live"] == "true"
    assert list(wide_rows[0].keys())[7:13] == ["S3", "Q0A", "Q0B", "Q1", "Q2", "Q3"]

    counts = manifest["counts"]
    assert counts["respondents"] == 3 and counts["answers"] == 117 and counts["fallback_answers"] == 0
    assert manifest["summary"]["Q30_attention_check"]["pass_rate"] == 1.0
    assert manifest["tokens"]["prompt"] == 30
    index = list(csv.DictReader(open(args.out_dir / "index.csv", newline="", encoding="utf-8-sig")))
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
    with open(Path(manifest["run_dir"]) / "answers_long.csv", newline="", encoding="utf-8-sig") as handle:
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


def test_questions_csv_carries_preambles_and_the_manifest_records_the_description_policy(tmp_path: Path, persona_csv: Path, survey) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(
        model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
        args=args, client=StubClient(survey), census_lookup={},
    )
    assert manifest["status"] == "completed", manifest["guardrails"]
    assert manifest["survey_description_sent"] is False
    run_dir = Path(manifest["run_dir"])
    with open(run_dir / "questions.csv", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == ["question_id", "question_type", "min_value", "max_value", "options", "text", "preamble"]
    by_id = {row["question_id"]: row for row in rows}
    assert "117-square-foot" in by_id["Q1"]["preamble"]
    assert "Concept 1: Backyard Home Office" in by_id["Q9A"]["preamble"]
    assert by_id["S3"]["preamble"] == ""
    prompt_sample = (run_dir / "prompt_sample.txt").read_text(encoding="utf-8")
    assert '"preamble"' in prompt_sample and "117-square-foot" in prompt_sample
    assert "What was cut" not in prompt_sample
    assert survey.description is not None  # the shared fixture was copied, not mutated
    kept = _args(tmp_path, persona_csv, survey_description="keep", run_tag="keep")
    manifest_keep = run_survey.run_one(
        model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
        args=kept, client=StubClient(survey), census_lookup={},
    )
    assert manifest_keep["survey_description_sent"] is True
    assert "What was cut" in (Path(manifest_keep["run_dir"]) / "prompt_sample.txt").read_text(encoding="utf-8")


def test_csv_outputs_start_with_bom_and_read_cleanly(tmp_path: Path, persona_csv: Path, survey) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey,
                                  contexts=run_survey.load_contexts(), args=args, client=StubClient(survey), census_lookup={})
    run_dir = Path(manifest["run_dir"])
    for name in ("answers_long.csv", "answers_wide.csv", "questions.csv"):
        assert (run_dir / name).read_bytes()[:3] == b"\xef\xbb\xbf", name
        with open(run_dir / name, newline="", encoding="utf-8-sig") as handle:
            header = csv.DictReader(handle).fieldnames
        assert header[0] in ("run_id", "question_id"), header[0]  # no stray BOM inside the first column name
    assert (args.out_dir / "index.csv").read_bytes()[:3] == b"\xef\xbb\xbf"


def test_persona_ids_filter_keeps_file_order_and_rejects_unknown(tmp_path: Path, persona_csv: Path) -> None:
    ids_file = tmp_path / "panel.txt"
    ids_file.write_text("# panel\nP003\nP001\n\n", encoding="utf-8")
    ids = run_survey.read_persona_ids(ids_file)
    assert ids == ["P003", "P001"]
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full", persona_ids=ids)
    assert [p.persona_id for p in personas] == ["P001", "P003"]  # file order, not list order
    with pytest.raises(ValueError, match="P999"):
        run_survey.load_personas(persona_csv, limit=None, prompt_variant="full", persona_ids=["P001", "P999"])
    (tmp_path / "dup.txt").write_text("P001\nP001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        run_survey.read_persona_ids(tmp_path / "dup.txt")


def test_run_id_panel_suffix() -> None:
    from datetime import datetime, timezone
    now = datetime(2026, 9, 12, 1, 2, 3, tzinfo=timezone.utc)
    assert run_survey.make_run_id("qwen/qwen3.7-plus", 1, limit=None, tag="matched", now=now, panel_size=150) == "20260912T010203Z_qwen3.7-plus_r1_p150_matched"
    assert run_survey.make_run_id("qwen/qwen3.7-plus", 2, limit=5, tag=None, now=now) == "20260912T010203Z_qwen3.7-plus_r2_n5"


def test_manifest_records_the_panel_file(tmp_path: Path, persona_csv: Path, survey) -> None:
    ids_file = tmp_path / "panel.txt"
    ids_file.write_text("P002\nP003\n", encoding="utf-8")
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full", persona_ids=run_survey.read_persona_ids(ids_file))
    args = _args(tmp_path, persona_csv, persona_ids=ids_file)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey,
                                  contexts=run_survey.load_contexts(), args=args, client=StubClient(survey), census_lookup={})
    assert manifest["personas"]["rows_used"] == 2
    assert manifest["personas"]["persona_ids_file"] == str(ids_file)
    assert len(manifest["personas"]["persona_ids_sha256"]) == 64
    assert "_p2" in manifest["run_id"]


def test_temperature_jitter_is_per_persona_and_deterministic(survey, persona_csv: Path) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    product, market = run_survey.load_contexts()
    builder = run_survey.TaggingPromptBuilder(run_survey.prompt_builder, max_tokens=4000, temperature=0.2, jitter=0.3, seed=202609091)
    temps = [builder.build_openrouter_prompt_payload(persona=p, survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None)["temperature"] for p in personas]
    assert len(set(temps)) > 1 and all(0.0 <= t <= 0.5 for t in temps)
    again = run_survey.TaggingPromptBuilder(run_survey.prompt_builder, max_tokens=4000, temperature=0.2, jitter=0.3, seed=202609091)
    assert temps == [again.build_openrouter_prompt_payload(persona=p, survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None)["temperature"] for p in personas]
    plain = run_survey.TaggingPromptBuilder(run_survey.prompt_builder, max_tokens=4000, temperature=0.2)
    assert plain.build_openrouter_prompt_payload(persona=personas[0], survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None)["temperature"] == 0.2
    assert run_survey.persona_temperature(1.4, 0.3, 1, "P001") <= 1.5 and run_survey.persona_temperature(0.1, 0.3, 1, "P001") >= 0.0


def test_no_sponsor_context_removes_goal_and_objections(tmp_path: Path, persona_csv: Path, survey) -> None:
    product, market = run_survey.neutral_contexts(*run_survey.load_contexts())
    assert product.primary_goal is None and product.main_barriers_or_concerns == [] and market.common_objections == []
    assert product.product_name == "Tahoe Mini" and product.price_range
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv, no_sponsor_context=True)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
                                  args=args, client=StubClient(survey), census_lookup={})
    sample = (Path(manifest["run_dir"]) / "prompt_sample.txt").read_text(encoding="utf-8")
    assert "Validate demand" not in sample and "Price sensitivity" not in sample and "Tahoe Mini" in sample
    assert manifest["context"]["sponsor_context_removed"] is True


def test_trait_mix_assigns_deterministic_shares_and_reaches_prompt_and_wide(tmp_path: Path, persona_csv: Path, survey) -> None:
    assert run_survey.parse_trait_mix("skeptical:0.5,enthusiastic:0.25") == [("skeptical", 0.5), ("enthusiastic", 0.25)]
    with pytest.raises(ValueError):
        run_survey.parse_trait_mix("skeptical:0.8,enthusiastic:0.5")
    with pytest.raises(ValueError):
        run_survey.parse_trait_mix("grumpy:0.1")
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    assigned = run_survey.assign_traits(personas, [("skeptical", 0.34)], seed=7)
    assert len(assigned) == 1 and assigned == run_survey.assign_traits(personas, [("skeptical", 0.34)], seed=7)
    args = _args(tmp_path, persona_csv, trait_mix="skeptical:0.34")
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=7, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
                                  args=args, client=StubClient(survey), census_lookup={})
    assert manifest["trait_mix"] == "skeptical:0.34" and manifest["trait_counts"] == {"skeptical": 1}
    with open(Path(manifest["run_dir"]) / "answers_wide.csv", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert "trait" in rows[0] and sum(1 for r in rows if r["trait"] == "skeptical") == 1
    sample = (Path(manifest["run_dir"]) / "prompt_sample.txt").read_text(encoding="utf-8")
    traited = next(p for p in personas if p.trait)
    if traited.persona_id == personas[0].persona_id:
        assert run_survey.TRAITS["skeptical"][:30] in sample


def test_reason_per_answer_is_requested_and_captured(tmp_path: Path, persona_csv: Path, survey) -> None:
    assert run_survey.reasons_from_raw('{"answers": [{"question_id": "Q1", "answer": 2, "reason": "too pricey"}, {"question_id": "Q2", "answer": 2}]}') == {"Q1": "too pricey"}
    assert run_survey.reasons_from_raw("not json") == {}
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv, reason_per_answer=True)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
                                  args=args, client=StubClient(survey, reasons=True), census_lookup={})
    assert manifest["reason_per_answer"] is True and manifest["counts"]["answers_with_reason"] == 3 * 39
    sample = (Path(manifest["run_dir"]) / "prompt_sample.txt").read_text(encoding="utf-8")
    assert '"reason"' in sample and "one-sentence" in sample and "max_tokens=9000" in sample
    with open(Path(manifest["run_dir"]) / "answers_long.csv", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["reason"] == "because S3"


def test_questions_per_call_splits_the_survey_and_stitches_answers(tmp_path: Path, persona_csv: Path, survey) -> None:
    chunks = run_survey.chunk_questions(survey, 10)
    assert [len(c.questions) for c in chunks] == [10, 10, 10, 9] and chunks[0].questions[0].id == "S3" and chunks[-1].questions[-1].id == "Q30"
    assert run_survey.chunk_questions(survey, 0) == [survey]
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    args = _args(tmp_path, persona_csv, questions_per_call=10)
    args.out_dir.mkdir(parents=True)
    client = StubClient(survey)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
                                  args=args, client=client, census_lookup={})
    assert manifest["status"] == "completed" and manifest["questions_per_call"] == 10 and manifest["calls_per_persona"] == 4
    assert client.stats["calls"] == 3 * 4 and manifest["counts"]["answers"] == 117 and manifest["counts"]["fallback_answers"] == 0
    with open(Path(manifest["run_dir"]) / "answers_wide.csv", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["persona_id"] for r in rows] == ["P001", "P002", "P003"] and rows[0]["Q30"] == "Moderately interested"
    raw = [json.loads(line) for line in open(Path(manifest["run_dir"]) / "raw_responses.jsonl", encoding="utf-8")]
    assert len(raw) == 3 and len(raw[0]["chunks"]) == 4 and raw[0]["parsed_ok"] is True


def test_region_state_and_housing_cost_basis_reach_the_census_record(tmp_path: Path, persona_csv: Path) -> None:
    # The Sept 16 matched export added these three Census-grounded columns; county is blank on 450 rows there.
    assert [c for c in ("region", "state", "housing_cost_basis") if c in run_survey.CENSUS_COLUMNS] == ["region", "state", "housing_cost_basis"]
    without = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")[0]
    assert "state" not in (without.census_record or {})  # older files: absent, not null
    path = tmp_path / "with_state.csv"
    with open(persona_csv, newline="", encoding="utf-8") as src, open(path, "w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=list(reader.fieldnames) + ["region", "state", "housing_cost_basis"])
        writer.writeheader()
        for row in reader:
            writer.writerow({**row, "region": "South", "state": "Texas", "housing_cost_basis": "owner costs"})
    persona = run_survey.load_personas(path, limit=None, prompt_variant="full")[0]
    assert persona.census_record["state"] == "Texas" and persona.census_record["region"] == "South" and persona.census_record["housing_cost_basis"] == "owner costs"
    assert '"state": "Texas"' in json.dumps(persona.model_dump())


def test_dry_run_prices_every_slice_under_questions_per_call(tmp_path: Path, persona_csv: Path, survey, capsys) -> None:
    personas = run_survey.load_personas(persona_csv, limit=1, prompt_variant="full")
    base = _args(tmp_path, persona_csv, models=["deepseek/deepseek-v4-pro-0813"], repeats=1, seed_base=1, dry_run=True)
    run_survey.dry_run(personas=personas, survey=survey, contexts=run_survey.load_contexts(), args=base)
    one_call = capsys.readouterr().out
    sliced = _args(tmp_path, persona_csv, models=["deepseek/deepseek-v4-pro-0813"], repeats=1, seed_base=1, dry_run=True, questions_per_call=10)
    run_survey.dry_run(personas=personas, survey=survey, contexts=run_survey.load_contexts(), args=sliced)
    four_calls = capsys.readouterr().out
    def usd(text: str) -> float:
        return float(next(line for line in text.splitlines() if "per run x" in line).split("~$")[1].split()[0])
    # Four slices each repeat the persona and the context; the questions are not repeated, so the
    # estimate grows but stays under 4x (the test fixture's persona is tiny, so the ratio is small here).
    assert 1.0 < usd(four_calls) / usd(one_call) < 4.0
    assert "input tokens across 4 calls" in four_calls


def test_interest_note_is_added_to_the_system_message_and_recorded(tmp_path: Path, persona_csv: Path, survey) -> None:
    personas = run_survey.load_personas(persona_csv, limit=None, prompt_variant="full")
    product, market = run_survey.load_contexts()
    plain = run_survey.TaggingPromptBuilder(run_survey.prompt_builder, max_tokens=4000, temperature=0.2)
    noted = run_survey.TaggingPromptBuilder(run_survey.prompt_builder, max_tokens=4000, temperature=0.2, respondent_note=run_survey.INTEREST_NOTE)
    kwargs = dict(persona=personas[0], survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None)
    a, b = plain.build_openrouter_prompt_payload(**kwargs), noted.build_openrouter_prompt_payload(**kwargs)
    assert run_survey.INTEREST_NOTE not in a["messages"][0]["content"] and b["messages"][0]["content"].endswith(run_survey.INTEREST_NOTE)
    assert a["messages"][1]["content"] == b["messages"][1]["content"]  # the context and the survey are untouched
    assert "whether or not you could pay for it" in run_survey.INTEREST_NOTE and "can have different answers" in run_survey.INTEREST_NOTE
    args = _args(tmp_path, persona_csv, interest_note=True)
    args.out_dir.mkdir(parents=True)
    manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
                                  args=args, client=StubClient(survey), census_lookup={})
    assert manifest["respondent_note"] == run_survey.INTEREST_NOTE
    assert run_survey.INTEREST_NOTE in (Path(manifest["run_dir"]) / "prompt_sample.txt").read_text(encoding="utf-8")
    plain_manifest = run_survey.run_one(model="stub/model", repeat=1, seed=1, personas=personas, survey=survey, contexts=run_survey.load_contexts(),
                                        args=_args(tmp_path, persona_csv, run_tag="plain"), client=StubClient(survey), census_lookup={})
    assert plain_manifest["respondent_note"] is None


def test_response_style_is_the_same_persona_in_every_repeat():
    """A style is a property of the respondent, so re-dealing it per repeat is a bug.

    When assign_traits was seeded on the per-repeat seed, only 22 of 100 personas kept their style
    between repeat 1 and repeat 2, and the fall in repeat agreement that followed was largely
    measuring the re-deal rather than the panel becoming less deterministic.
    """
    mix = run_survey.parse_trait_mix("skeptical:0.25,enthusiastic:0.20,pragmatic:0.20,indifferent:0.15")
    personas = [types.SimpleNamespace(persona_id=f"P{i:03d}") for i in range(1, 101)]
    base = 20260909
    first = run_survey.assign_traits(personas, mix, base)
    second = run_survey.assign_traits(personas, mix, base)
    assert first == second, "same seed_base must deal the same styles"
    assert sum(1 for p in personas if first.get(p.persona_id)) == 80
    # and the per-repeat seed, which is what the bug used, would have dealt a different hand
    assert run_survey.assign_traits(personas, mix, base * 10 + 1) != first
