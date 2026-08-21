"""F-06 / F-15 regressions: segment ranking must not invent or self-contradict.

`_segment_score_table` only scores a segment when it has numeric answers for the Neo question ids
Q0B / Q1 / Q2. For any survey that does not use those ids the table is empty, and the previous
implementation fell back to the *alphabetically first* segment label — a fabricated finding that was
also injected into the evidence package handed to the summarising model. When exactly one segment
scored, `max` and `min` returned the same key, so the same segment was reported as both strongest
and weakest.
"""

from __future__ import annotations

import pandas as pd

from src.adapters.legacy_backend.domain import (
    _compute_strongest_segment,
    _compute_weakest_segment,
    build_insights_view,
)


def _records(rows: list[tuple[str, str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["segment_label", "question_id", "answer"])


def test_strongest_segment_is_unavailable_when_no_scoreable_question_exists():
    """A non-Neo survey has no Q0B/Q1/Q2, so no segment can be ranked."""
    df = _records(
        [
            ("Balanced Mainstream", "BENEFIT", "Automatic scheduling"),
            ("Remote Professionals", "BENEFIT", "Deadline reminders"),
            ("Balanced Mainstream", "PRICE", "12"),
            ("Remote Professionals", "PRICE", "10"),
        ]
    )

    assert _compute_strongest_segment(df) is None, (
        "with nothing scoreable the metric must report unavailable rather than "
        "returning the alphabetically first segment"
    )


def test_strongest_and_weakest_are_unavailable_with_only_one_scoreable_segment():
    """One segment cannot be simultaneously the strongest and the weakest."""
    df = _records(
        [
            ("Balanced Mainstream", "Q1", 4),
            ("Balanced Mainstream", "Q2", 5),
            ("Remote Professionals", "CONCERN", "too many subscriptions"),
        ]
    )

    strongest = _compute_strongest_segment(df)
    weakest = _compute_weakest_segment(df)

    assert strongest is None
    assert weakest is None


def test_strongest_and_weakest_rank_two_scoreable_segments():
    """The Neo happy path must keep working: a real comparison still ranks correctly."""
    df = _records(
        [
            ("Remote Professionals", "Q1", 5),
            ("Remote Professionals", "Q2", 5),
            ("Wellness-Oriented", "Q1", 2),
            ("Wellness-Oriented", "Q2", 2),
        ]
    )

    assert _compute_strongest_segment(df) == "Remote Professionals"
    assert _compute_weakest_segment(df) == "Wellness-Oriented"


def _custom_run_payload() -> dict:
    def record(segment: str, question_id: str, answer: object) -> dict:
        return {
            "respondent_id": f"RESP_{segment[:3]}",
            "model": "openai/gpt-4o-mini",
            "question_id": question_id,
            "question_text": question_id.title(),
            "question_type": "single_choice",
            "answer": answer,
            "segment_label": segment,
            "experiment_mode": "split",
            "survey_title": "StudyFlow FocusPlan Study",
        }

    return {
        "run_id": "run_custom_001",
        "status": "completed",
        "survey_title": "StudyFlow FocusPlan Study",
        "response_records": [
            record("Balanced Mainstream", "BENEFIT", "Automatic study scheduling"),
            record("Remote Professionals", "BENEFIT", "Deadline reminders"),
            record("Balanced Mainstream", "CONCERN", "subscription fatigue"),
            record("Remote Professionals", "CONCERN", "privacy"),
        ],
    }


def test_evidence_package_omits_strongest_segment_when_it_cannot_be_computed(test_settings):
    """The fabricated segment must never reach the model that writes the summary.

    The evidence package is handed to the summarising LLM with instructions not to contradict it,
    so an invented 'strongest segment' becomes an authoritative-sounding finding.
    """
    view = build_insights_view(
        settings=test_settings,
        study_mode="general",
        latest_run_payload=_custom_run_payload(),
    )

    evidence_ids = {item.get("id") for item in view["evidence_package"]["items"]}
    assert "exec_strongest_segment" not in evidence_ids

    blob = str(view["evidence_package"]["items"])
    assert "shows the strongest overall interest-oriented pattern" not in blob
