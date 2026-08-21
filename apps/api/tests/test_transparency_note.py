"""The methodological caveat must reach every surface that shows findings.

The backend has always returned `transparency_note` on both the analysis and insights responses. For
most of this QA pass nothing rendered it, so the pages showing numbers carried no statement that the
results are exploratory or that the confidence and agreement labels are rule-based rather than
inferential. Insights renders it now; Analysis is charts and question statistics, which are findings
too.

This asserts the contract the UI depends on, so the note cannot quietly stop being sent.
"""

from __future__ import annotations

from src.adapters.legacy_backend.domain import build_analysis_view, build_insights_view

from tests.test_fallback_exclusion import _payload


def _analysis(test_settings):
    return build_analysis_view(
        settings=test_settings,
        study_mode="neo_smart",
        latest_run_payload=_payload(),
        survey_payload=None,
        question_id="Q1",
        model=None,
        segment=None,
        records_limit=50,
        records_offset=0,
        open_text_limit=5,
    )


def test_both_findings_surfaces_carry_the_caveat(test_settings):
    analysis = _analysis(test_settings)
    insights = build_insights_view(
        settings=test_settings, study_mode="neo_smart", latest_run_payload=_payload()
    )

    # Asserted by meaning, not by phrase: the two surfaces word the caveat differently and both are
    # accurate. What must not vary is that each one says the results are provisional, that the labels
    # are rule-based, and that findings need human respondents before they are relied on.
    for name, view in (("analysis", analysis), ("insights", insights)):
        note = (view.get("transparency_note") or "").lower()
        assert note, f"{name} shipped no transparency note"
        assert any(word in note for word in ("exploratory", "hypothesis generation")), note
        assert "rule-based" in note or "deterministic" in note, note
        assert "real respondents" in note, note


def test_the_caveat_states_the_labels_are_rule_based(test_settings):
    """Confidence and agreement are heuristics; the note is the only place that says so."""
    note = _analysis(test_settings)["transparency_note"].lower()

    assert "confidence" in note and "agreement" in note
    assert "rule-based" in note or "deterministic" in note
