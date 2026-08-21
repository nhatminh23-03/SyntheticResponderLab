"""F-13: a Likert chart must put its counts on the scale points it declares.

Models answer Likert questions numerically (3, 4). The distribution is keyed on the answer's display
value, so a question whose declared options are named scale points — "Not at all interested" …
"Extremely interested" — matched nothing: every named point rendered at 0% and the counts appeared in
extra, unlabelled buckets called "3" and "4".

17 of the Neo survey's 24 Likert questions are affected, including the whole interest ladder
(Q0B, Q1, Q2) and every positioning concept pair (Q9A–Q13B). The 7 Q5_* barrier items declare no
options, fall back to numeric labels, and were already correct.
"""

from __future__ import annotations

import pandas as pd

from src.adapters.legacy_backend.domain import _shape_distribution_rows

NAMED_SCALE = [
    "Not at all interested",
    "Slightly interested",
    "Moderately interested",
    "Very interested",
    "Extremely interested",
]


def _distribution(pairs: list[tuple[str, int]]) -> pd.DataFrame:
    total = sum(count for _, count in pairs) or 1
    return pd.DataFrame(
        [
            {"answer_display": label, "count": count, "percentage": round(count / total * 100, 1)}
            for label, count in pairs
        ]
    )


def test_numeric_likert_answers_land_on_the_declared_scale_points():
    rows = _shape_distribution_rows(
        _distribution([("3", 1), ("4", 5)]),
        chart_kind="likert",
        declared_options=NAMED_SCALE,
        scale_min=1,
        scale_max=5,
    )

    by_label = {row["label"]: row["count"] for row in rows}
    assert by_label["Moderately interested"] == 1
    assert by_label["Very interested"] == 5
    assert by_label["Not at all interested"] == 0


def test_numeric_likert_answers_do_not_leave_unlabelled_extra_buckets():
    rows = _shape_distribution_rows(
        _distribution([("3", 1), ("4", 5)]),
        chart_kind="likert",
        declared_options=NAMED_SCALE,
        scale_min=1,
        scale_max=5,
    )

    assert [row["label"] for row in rows] == NAMED_SCALE, (
        "the chart must show exactly the declared scale points, not numeric duplicates"
    )
    assert sum(row["count"] for row in rows) == 6


def test_out_of_range_values_are_kept_visible_rather_than_forced_onto_the_scale():
    """A value outside the declared range is a data problem; hiding it would mask it."""
    rows = _shape_distribution_rows(
        _distribution([("4", 2), ("9", 1)]),
        chart_kind="likert",
        declared_options=NAMED_SCALE,
        scale_min=1,
        scale_max=5,
    )

    labels = [row["label"] for row in rows]
    assert "9" in labels, "an out-of-range answer must remain visible"
    assert {row["label"]: row["count"] for row in rows}["Very interested"] == 2


def test_numeric_labelled_scales_are_unchanged():
    """Q5_* style questions declare no named options and already matched correctly."""
    rows = _shape_distribution_rows(
        _distribution([("3", 2), ("5", 1)]),
        chart_kind="likert",
        declared_options=["1", "2", "3", "4", "5"],
        scale_min=1,
        scale_max=5,
    )

    by_label = {row["label"]: row["count"] for row in rows}
    assert by_label["3"] == 2
    assert by_label["5"] == 1


def test_categorical_questions_are_unaffected():
    rows = _shape_distribution_rows(
        _distribution([("Yes", 4), ("No", 2)]),
        chart_kind="categorical_bar",
        declared_options=["Yes", "No", "Maybe"],
    )

    by_label = {row["label"]: row["count"] for row in rows}
    assert by_label["Yes"] == 4
    assert by_label["Maybe"] == 0
