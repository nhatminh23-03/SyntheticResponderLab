"""F-17: Insights must say why an all-fabricated run has nothing to show.

`build_insights_view` splits live answers from deterministic filler and then checks whether any live
answers remain. When none do, it returned the message written for a run that has not stored anything
yet -- "The latest run does not include response records yet." -- for a run holding a full set of
records, and dropped the `answer_sourcing` summary that would have explained the real reason.

Analysis, given the same run, says what actually happened and reports the sourcing. The two surfaces
disagreed about the same run, and the one that was wrong was the one that omitted the evidence.
"""

from __future__ import annotations

from typing import Any

from src.adapters.legacy_backend.domain import build_analysis_view, build_insights_view


def _record(answer: Any, *, is_fallback: bool, respondent: str) -> dict:
    return {
        "respondent_id": respondent,
        "model": "openai/gpt-4o-mini",
        "experiment_mode": "split",
        "survey_title": "QA Survey",
        "question_id": "Q1",
        "question_text": "How interested are you?",
        "question_type": "likert",
        "answer": answer,
        "segment_label": "Remote Professionals",
        "run_id": "run_qa_001",
        "is_fallback": is_fallback,
    }


def _all_fabricated_payload() -> dict:
    """A run that completed: four saved records, none of them a model's answer."""
    return {
        "run_id": "run_qa_001",
        "status": "completed",
        "survey_title": "QA Survey",
        "response_records": [
            _record(3, is_fallback=True, respondent=f"RESP_{index:03d}") for index in range(1, 5)
        ],
    }


def _empty_payload() -> dict:
    return {"run_id": "run_qa_002", "status": "completed", "survey_title": "QA Survey", "response_records": []}


def _insights(test_settings, payload):
    return build_insights_view(
        settings=test_settings, study_mode="neo_smart", latest_run_payload=payload
    )


def _analysis(test_settings, payload):
    return build_analysis_view(
        settings=test_settings,
        study_mode="neo_smart",
        latest_run_payload=payload,
        survey_payload=None,
        question_id="Q1",
        model=None,
        segment=None,
        records_limit=50,
        records_offset=0,
        open_text_limit=5,
    )


def test_insights_explains_that_every_answer_was_fabricated(test_settings):
    view = _insights(test_settings, _all_fabricated_payload())

    assert view["available"] is False
    assert "does not include response records" not in view["message"], (
        "the run holds four records; saying it has none names the wrong cause"
    )
    assert "deterministic filler" in view["message"]


def test_insights_reports_the_sourcing_that_explains_the_refusal(test_settings):
    """The number that justifies the refusal has to travel with it."""
    view = _insights(test_settings, _all_fabricated_payload())
    sourcing = view["answer_sourcing"]

    assert sourcing is not None, "the reader is told the run is unusable and given nothing to check"
    assert sourcing["live_answers_used"] == 0
    assert sourcing["fallback_answers_excluded"] == 4
    assert sourcing["total_answers"] == 4
    assert sourcing["live_answer_rate"] == 0.0


def test_analysis_and_insights_agree_about_the_same_run(test_settings):
    payload = _all_fabricated_payload()
    analysis = _analysis(test_settings, payload)
    insights = _insights(test_settings, payload)

    assert analysis["available"] == insights["available"] is False
    assert analysis["answer_sourcing"] == insights["answer_sourcing"]


def test_a_run_with_no_records_at_all_still_says_so(test_settings):
    """Guard against over-correcting: an empty run is a different thing and keeps its own message."""
    view = _insights(test_settings, _empty_payload())

    assert view["available"] is False
    assert "does not include response records" in view["message"]
    assert "deterministic filler" not in view["message"]
