"""F-06(b): a Custom Study must not be told about the Neo survey's schema.

When an insight cannot be computed the builders explained *why* in Neo's own vocabulary — "Primary use
question Q3 was not found", "Barrier matrix items", "Positioning concept pairs", "Core decision-ladder
questions". For a study about a coffee subscription or a study-planning app those names mean nothing and
imply the researcher did something wrong.

Neo keeps the diagnostic wording, because there the schema is known and the message is actionable.
"""

from __future__ import annotations

from src.adapters.legacy_backend.domain import build_insights_view

NEO_VOCABULARY = ["Q3", "barrier matrix", "concept pair", "decision-ladder", "decision ladder", "Neo"]

UNAVAILABLE_CHARTS = ["barrier_ranking", "message_performance", "use_case_share", "interest_ladder"]


def _custom_payload() -> dict:
    def record(question_id: str, answer, respondent: str) -> dict:
        return {
            "respondent_id": respondent,
            "model": "openai/gpt-4o-mini",
            "experiment_mode": "split",
            "survey_title": "StudyFlow FocusPlan Study",
            "question_id": question_id,
            "question_text": question_id.title(),
            "question_type": "single_choice",
            "answer": answer,
            "segment_label": "Balanced Mainstream",
            "run_id": "run_custom_001",
        }

    return {
        "run_id": "run_custom_001",
        "status": "completed",
        "survey_title": "StudyFlow FocusPlan Study",
        "response_records": [
            record("BENEFIT", "Automatic study scheduling", "RESP_001"),
            record("CONCERN", "subscription fatigue", "RESP_002"),
        ],
    }


def _charts(test_settings, study_mode: str) -> dict:
    view = build_insights_view(
        settings=test_settings, study_mode=study_mode, latest_run_payload=_custom_payload()
    )
    return view["charts"]


def test_custom_study_unavailable_messages_use_generic_wording(test_settings):
    charts = _charts(test_settings, "general")

    for name in UNAVAILABLE_CHARTS:
        chart = charts[name]
        assert chart["available"] is False, f"{name} should be unavailable for this survey"
        assert chart["message"] == "This insight is not applicable to this survey.", (
            f"{name} still explains itself in Neo's vocabulary: {chart['message']!r}"
        )


def test_custom_study_messages_never_mention_the_neo_schema(test_settings):
    charts = _charts(test_settings, "general")
    blob = " ".join(str(charts[name].get("message") or "") for name in UNAVAILABLE_CHARTS).lower()

    for term in NEO_VOCABULARY:
        assert term.lower() not in blob, f"Neo vocabulary leaked into a Custom Study: {term!r}"


def test_neo_study_keeps_the_diagnostic_wording(test_settings):
    """In Neo the schema is known, so naming the missing question is actionable rather than confusing."""
    charts = _charts(test_settings, "neo_smart")

    assert "Q3" in charts["use_case_share"]["message"]
    assert "arrier" in charts["barrier_ranking"]["message"]
