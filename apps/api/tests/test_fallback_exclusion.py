"""F-04: deterministic filler must not be counted as evidence.

Fabricated answers are schema-valid and stamped with the real model name, so until now they were
averaged into every mean, percentage and ranking exactly as if a model had produced them. They stay in
the raw dataset with provenance — they are never deleted — but they are excluded from the analytical
surfaces by default, and the exclusion is reported.
"""

from __future__ import annotations

from typing import Any

from src.adapters.legacy_backend.domain import build_analysis_view, build_insights_view


def _record(question_id: str, answer: Any, *, is_fallback: bool, respondent: str = "RESP_001") -> dict:
    return {
        "respondent_id": respondent,
        "model": "openai/gpt-4o-mini",
        "experiment_mode": "split",
        "survey_title": "QA Survey",
        "question_id": question_id,
        "question_text": "How interested are you?",
        "question_type": "likert",
        "answer": answer,
        "segment_label": "Remote Professionals",
        "run_id": "run_qa_001",
        "is_fallback": is_fallback,
    }


def _payload() -> dict:
    # Three live 5s and one fabricated 1: the mean is 5.0 live, 4.0 if the filler is counted.
    return {
        "run_id": "run_qa_001",
        "status": "completed",
        "survey_title": "QA Survey",
        "response_records": [
            _record("Q1", 5, is_fallback=False, respondent="RESP_001"),
            _record("Q1", 5, is_fallback=False, respondent="RESP_002"),
            _record("Q1", 5, is_fallback=False, respondent="RESP_003"),
            _record("Q1", 1, is_fallback=True, respondent="RESP_004"),
        ],
    }


def _analysis(test_settings):
    return build_analysis_view(
        settings=test_settings,
        study_mode="general",
        latest_run_payload=_payload(),
        survey_payload=None,
        question_id="Q1",
        model=None,
        segment=None,
        records_limit=50,
        records_offset=0,
        open_text_limit=5,
    )


def test_charts_exclude_fabricated_answers(test_settings):
    analysis = _analysis(test_settings)
    card = next(c for c in analysis["dashboard"]["questions"] if c["question_id"] == "Q1")

    assert card["response_count"] == 3, "only live answers may be counted"
    total = sum(int(bucket.get("count") or 0) for bucket in card["distribution"])
    assert total == 3


def test_dataset_summary_counts_live_answers_only(test_settings):
    analysis = _analysis(test_settings)
    assert analysis["summary"]["total_records"] == 3


def test_analysis_reports_what_it_excluded(test_settings):
    analysis = _analysis(test_settings)
    sourcing = analysis["answer_sourcing"]

    assert sourcing["live_answers_used"] == 3
    assert sourcing["fallback_answers_excluded"] == 1
    assert sourcing["live_answer_rate"] == 0.75


def test_fabricated_records_remain_inspectable_and_are_not_deleted(test_settings):
    analysis = _analysis(test_settings)
    rows = analysis["records_preview"]["rows"]

    assert analysis["records_preview"]["total"] == 4, "the raw record view must still show every row"
    assert any(row.get("is_fallback") is True for row in rows), (
        "fabricated rows must stay visible in the raw dataset with their provenance"
    )


def test_insights_metrics_use_live_answers_only(test_settings):
    insights = build_insights_view(
        settings=test_settings, study_mode="general", latest_run_payload=_payload()
    )
    assert insights["executive_summary"]["average_interest"] == 5.0, (
        "the fabricated 1 must not drag the mean down to 4.0"
    )


def test_runs_saved_before_provenance_existed_are_treated_as_live(test_settings):
    """Older saved runs have no is_fallback key; excluding them all would erase historic results."""
    payload = _payload()
    for row in payload["response_records"]:
        row.pop("is_fallback")

    analysis = build_analysis_view(
        settings=test_settings,
        study_mode="general",
        latest_run_payload=payload,
        survey_payload=None,
        question_id="Q1",
        model=None,
        segment=None,
        records_limit=50,
        records_offset=0,
        open_text_limit=5,
    )
    assert analysis["summary"]["total_records"] == 4
    assert analysis["answer_sourcing"]["fallback_answers_excluded"] == 0
