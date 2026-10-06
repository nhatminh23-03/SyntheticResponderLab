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
        # A placeholder row (ruling R7): is_fallback "true" is not a model answer and must never reach the fixture.
        {"run_id": "r", "model": "google/gemini-3-flash-preview", "persona_id": "P002", "respondent_id": "RESP_002", "question_id": "Q3",
         "question_type": "single_choice", "answer": "Placeholder", "answer_json": "\"Placeholder\"", "is_fallback": "true"},
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


def test_skips_fallback_placeholder_rows_and_counts_them(tmp_path):
    answers, personas = _inputs(tmp_path)
    fixture = builder.build_fixture(answers, personas, run_label="R021 r1", run_date="2026-10-03")
    second = fixture["respondents"][1]
    assert second["respondent_id"] == "RESP_002"
    assert "Q3" not in second["answers"]                       # the placeholder row is absent
    assert second["answers"] == {"Q1": 1}
    assert "Placeholder" not in json.dumps(fixture)
    assert fixture["source"]["skipped_fallback_rows"] == 1


def test_fallback_flag_is_case_insensitive_and_a_missing_column_counts_as_false(tmp_path):
    answers, personas = _inputs(tmp_path)
    rows = list(csv.DictReader(answers.open(newline="", encoding="utf-8")))
    rows[3]["is_fallback"] = " TRUE "                          # case and stray spaces still mean "true"
    rows[0]["is_fallback"] = "False"
    header = [c for c in rows[0].keys()]
    _write(answers, header, rows)
    fixture = builder.build_fixture(answers, personas, run_label="x", run_date="2026-10-03")
    assert fixture["source"]["skipped_fallback_rows"] == 1
    assert fixture["respondents"][0]["answers"] == {"Q1": 4, "Q3": "Home office"}
    assert "Q3" not in fixture["respondents"][1]["answers"]

    no_flag_header = [c for c in header if c != "is_fallback"]
    no_flag_rows = [{k: v for k, v in row.items() if k != "is_fallback"} for row in rows]
    _write(answers, no_flag_header, no_flag_rows)
    fixture = builder.build_fixture(answers, personas, run_label="x", run_date="2026-10-03")
    assert fixture["source"]["skipped_fallback_rows"] == 0
    assert fixture["respondents"][1]["answers"] == {"Q1": 1, "Q3": "Placeholder"}


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
