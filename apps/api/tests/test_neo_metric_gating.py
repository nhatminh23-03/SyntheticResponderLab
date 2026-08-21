"""F-06: a Custom Study must never acquire Neo research meaning from its question ids.

The Neo insight metrics key on that survey's literal ids -- Q1, Q2, Q3, Q0B, S3, Q5_*, Q9A/Q9B..Q13A/Q13B.
`schema_normalizer` assigns `Q{index}` to any question that declares no id, so an ordinary uploaded survey
lands on those ids by default rather than by coincidence. When it does, the metrics report `available: true`
and describe the researcher's questions in Neo's terms.

The fixture below is shaped like the Cortado Roasters coffee-subscription preset that ships in the
repository, where this reproduces exactly:

    Q1  "How interested are you in a coffee subscription?"  -> reported as "Price-point interest"
    Q2  "About how much do you spend per month?"            -> reported as "Purchase likelihood"
    Q3  "Where do you most often buy coffee for home?"      -> reported as "Primary intended use"

Nothing in the run is wrong; the interpretation laid over it is.
"""

from __future__ import annotations

import json

from src.adapters.legacy_backend.domain import build_insights_view

# Meanings that belong to the Neo survey and to no other. If any of these reach a Custom Study payload,
# the study has been told something about itself that its own questions never asked.
NEO_MEANINGS = [
    "Price-point interest",
    "Purchase likelihood",
    "Primary intended use",
    "Top intended use",
    "Decision ladder",
    "Category interest",
    "Feasibility",
    "Positioning",
    "Barrier",
]

# Neo schema vocabulary that must never be shown to a researcher who did not write the Neo survey.
#
# Deliberately phrases rather than bare ids: a Custom Study legitimately echoes its *own* question ids
# back to the researcher ("Q3: segment differences observed ..."), and that is their question, not Neo's.
# What must not appear is Neo's schema being offered as an explanation of someone else's survey.
NEO_VOCABULARY = [
    "Primary use question",
    "Barrier matrix",
    "concept pair",
    "decision-ladder",
    "decision ladder",
    "Tahoe",
    "homeowner",
    "backyard",
    "Neo Smart",
    "Q0B",
]

MODELS = ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"]
SEGMENTS = ["Everyday Brewers", "Weekend Ritualists"]


def _record(question_id, question_text, question_type, answer, respondent, model, segment):
    return {
        "respondent_id": respondent,
        "model": model,
        "experiment_mode": "split",
        "survey_title": "Cortado Roasters — Everyday Origins Subscription Survey",
        "question_id": question_id,
        "question_text": question_text,
        "question_type": question_type,
        "answer": answer,
        "segment_label": segment,
        "run_id": "run_coffee_001",
    }


def _coffee_payload(ids: list[str]) -> dict:
    """A coffee-subscription run whose three questions can be given any ids the caller likes.

    Interest is a 1-5 rating, spend is a dollar band, and the last question is where the respondent
    buys coffee today. None of the three is a Neo question.
    """
    questions = [
        (ids[0], "How interested are you in a coffee subscription?", "likert"),
        (ids[1], "About how much do you spend on coffee per month?", "single_choice"),
        (ids[2], "Where do you most often buy coffee for home?", "single_choice"),
    ]
    answers = [
        [4, "$30 to $49", "Local coffee shop or roaster"],
        [2, "Under $15", "Supermarket or big-box store"],
        [5, "$50 to $79", "Local coffee shop or roaster"],
        [3, "$15 to $29", "Online retailer"],
    ]
    records = []
    for index, row in enumerate(answers):
        respondent = f"RESP_{index + 1:03d}"
        segment = SEGMENTS[index % len(SEGMENTS)]
        model = MODELS[index % len(MODELS)]
        for (question_id, question_text, question_type), answer in zip(questions, row):
            records.append(
                _record(question_id, question_text, question_type, answer, respondent, model, segment)
            )
    return {
        "run_id": "run_coffee_001",
        "status": "completed",
        "survey_title": "Cortado Roasters — Everyday Origins Subscription Survey",
        "models_used": list(MODELS),
        "experiment_mode": "split",
        "response_records": records,
    }


def _neo_payload() -> dict:
    """A Neo-shaped run: the decision ladder, a barrier matrix item, a concept pair, and primary use."""
    questions = [
        ("S3", "Outdoor space feasibility", "single_choice", ["Yes, definitely", "Yes, likely"]),
        ("Q0B", "Category interest", "likert", [5, 4]),
        ("Q1", "Purchase interest at $23,000", "likert", [5, 3]),
        ("Q2", "Purchase likelihood in 24 months", "likert", [4, 2]),
        ("Q3", "Primary intended use", "single_choice", ["Home office", "Home gym"]),
        ("Q5_1", "Barrier: Upfront price", "likert", [5, 4]),
        ("Q5_2", "Barrier: Permitting uncertainty", "likert", [3, 2]),
        ("Q10A", "Concept 10 appeal", "likert", [5, 3]),
        ("Q10B", "Concept 10 believability", "likert", [4, 3]),
    ]
    records = []
    for index in range(4):
        respondent = f"RESP_{index + 1:03d}"
        segment = ["Remote Professionals", "Wellness-Oriented"][index % 2]
        model = MODELS[index % len(MODELS)]
        for question_id, question_text, question_type, choices in questions:
            records.append(
                _record(
                    question_id,
                    question_text,
                    question_type,
                    choices[index % len(choices)],
                    respondent,
                    model,
                    segment,
                )
            )
    return {
        "run_id": "run_neo_001",
        "status": "completed",
        "survey_title": "Neo Smart Living Demo Survey",
        "models_used": list(MODELS),
        "experiment_mode": "split",
        "response_records": records,
    }


def _insights(test_settings, study_mode: str, payload: dict) -> dict:
    return build_insights_view(
        settings=test_settings, study_mode=study_mode, latest_run_payload=payload
    )


def test_custom_study_with_neo_ids_is_not_given_neo_meanings(test_settings):
    """The core invariant. Colliding ids must not import the Neo survey's research meaning."""
    view = _insights(test_settings, "general", _coffee_payload(["Q1", "Q2", "Q3"]))
    serialized = json.dumps(view)

    for meaning in NEO_MEANINGS:
        assert meaning not in serialized, (
            f"a coffee-subscription study was described using the Neo meaning {meaning!r}"
        )

    charts = view["charts"]
    for name in ("use_case_share", "interest_ladder", "barrier_ranking", "message_performance"):
        assert charts[name]["available"] is False, (
            f"{name} is a Neo metric and must not activate for a Custom Study"
        )

    summary = view["executive_summary"]
    assert summary["average_interest"] is None, (
        "average_interest averages the Neo decision-ladder questions; a dollar spend band is not one"
    )
    assert summary["strongest_segment"] is None
    assert summary["top_use_case"]["share"] is None


def test_renaming_custom_questions_does_not_change_their_meaning(test_settings):
    """The same answers must be read the same way whatever the questions are called.

    This is the property that was violated: identical data produced different research claims depending
    only on whether the ids happened to collide with Neo's.
    """
    colliding = _insights(test_settings, "general", _coffee_payload(["Q1", "Q2", "Q3"]))
    distinct = _insights(test_settings, "general", _coffee_payload(["C1", "C2", "C3"]))

    def comparable(view, ids):
        """Everything the study is said to show, with the researcher's own ids normalized away.

        Notes quote the question they describe, so `Q1: model differences observed` and
        `C1: model differences observed` are the same claim about the same question. The id is a
        name; this compares the meaning attached to it.
        """
        blob = json.dumps(
            {
                "charts": {name: chart.get("available") for name, chart in view["charts"].items()},
                "executive_summary": view["executive_summary"],
                "segment_story": view["segment_story"],
                "finding_titles": [finding.get("title") for finding in view["top_findings"]],
            }
        )
        for index, question_id in enumerate(ids):
            blob = blob.replace(question_id, f"<question-{index + 1}>")
        return json.loads(blob)

    assert comparable(colliding, ["Q1", "Q2", "Q3"]) == comparable(distinct, ["C1", "C2", "C3"]), (
        "renaming the questions changed what the study was said to show"
    )


def test_custom_unavailable_neo_metrics_use_generic_wording(test_settings):
    """A researcher must not be shown the Neo survey's schema as an explanation."""
    view = _insights(test_settings, "general", _coffee_payload(["Q1", "Q2", "Q3"]))

    for name in ("use_case_share", "interest_ladder", "barrier_ranking", "message_performance"):
        chart = view["charts"][name]
        assert chart["message"] == "This insight is not applicable to this survey.", (
            f"{name} explains itself in Neo's vocabulary: {chart['message']!r}"
        )

    serialized = json.dumps(view)
    for token in NEO_VOCABULARY:
        assert token not in serialized, f"Neo schema vocabulary {token!r} leaked into a Custom Study"


def test_generic_metrics_still_work_for_a_custom_study(test_settings):
    """Gating the Neo metrics must not take the survey-agnostic ones with them."""
    view = _insights(test_settings, "general", _coffee_payload(["Q1", "Q2", "Q3"]))

    assert view["available"] is True
    assert view["charts"]["model_difference"]["available"] is True, (
        "model comparison reads no question ids and must remain available"
    )
    assert any(finding.get("id") == "model-differences" for finding in view["top_findings"])
    assert view["answer_sourcing"]["live_answers_used"] == 12


def test_neo_study_keeps_its_own_metrics(test_settings):
    """Neo's schema is known, so its metrics stay exactly as they were."""
    view = _insights(test_settings, "neo_smart", _neo_payload())
    charts = view["charts"]

    assert charts["use_case_share"]["available"] is True
    assert charts["interest_ladder"]["available"] is True
    assert charts["barrier_ranking"]["available"] is True

    ladder_labels = {row["label"] for row in charts["interest_ladder"]["rows"]}
    assert {"Price-point interest", "Purchase likelihood"} <= ladder_labels

    summary = view["executive_summary"]
    assert summary["average_interest"] is not None
    assert summary["top_use_case"]["label"] in {"Home office", "Home gym"}

    titles = {finding.get("title") for finding in view["top_findings"]}
    assert "Top intended use" in titles
