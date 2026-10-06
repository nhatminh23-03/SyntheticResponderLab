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


def test_missing_answers_stay_missing():
    fixture_with_missing = {
        "source": {"run_label": "R021 r1", "run_date": "2026-10-03"},
        "question_ids": ["Q1", "Q0B"],
        "models_used": ["a/m1", "b/m2"],
        "respondents": [
            {"respondent_id": "RESP_001", "model": "a/m1", "persona": {"persona_id": "P001", "lifestyle_tags": []}, "answers": {"Q1": 4, "Q0B": 2}},
            {"respondent_id": "RESP_002", "model": "b/m2", "persona": {"persona_id": "P002", "lifestyle_tags": []}, "answers": {"Q1": 1}},
        ],
    }
    result = build_demo_run_result(survey_payload=SURVEY, experiment_payload={"sample_size": 2}, reason="requested", fixture=fixture_with_missing)
    records = result["response_records"]
    assert len(records) == 3
    resp2_q0b = [(r["respondent_id"], r["question_id"]) for r in records if r["respondent_id"] == "RESP_002" and r["question_id"] == "Q0b"]
    assert len(resp2_q0b) == 0
    assert all(r["answer"] is not None and r["answer"] != "" for r in records)


def test_fixture_data_is_copied_not_cached():
    result1 = build_demo_run_result(survey_payload=SURVEY, experiment_payload={"sample_size": 1}, reason="requested", fixture=FIXTURE)
    result1["personas"][0]["persona_id"] = "MUTATED"
    result2 = build_demo_run_result(survey_payload=SURVEY, experiment_payload={"sample_size": 1}, reason="requested", fixture=FIXTURE)
    assert result2["personas"][0]["persona_id"] == "P001"
