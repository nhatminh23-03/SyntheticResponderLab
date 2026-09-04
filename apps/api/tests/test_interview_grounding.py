from __future__ import annotations

import json

import pytest

from src.simulation import interview_grounding
from src.simulation.interview_prompt_builder import (
    build_judge_prompt,
    build_system_prompt,
)


QUESTIONS = [{"id": "IQ1", "text": "What is your reaction?"}]
ANSWERS = {"IQ1": "I would consider it after comparing the practical trade-offs."}


def test_interview_prompt_never_uses_fit_tier():
    persona = {
        "age_bucket": "40-49",
        "segment_label": "Homeowners",
        "awareness_stage": "aware",
    }

    strong_prompt = build_system_prompt({**persona, "fit_tier": "strong"}, None, None)
    edge_prompt = build_system_prompt({**persona, "fit_tier": "edge"}, None, None)

    assert strong_prompt == edge_prompt
    assert "fit_tier" not in strong_prompt


def test_judge_prompt_scores_fit_tier_when_real_tier_exists():
    system_prompt, user_prompt = build_judge_prompt(
        QUESTIONS,
        ANSWERS,
        ANSWERS,
        {"fit_tier": " Strong ", "segment_label": "Homeowners"},
    )

    assert 'fit_tier="strong"' in system_prompt
    assert "across 4 grounding dimensions" in system_prompt
    assert "fit_tier_alignment" in system_prompt
    assert "fit_tier_alignment" in user_prompt


@pytest.mark.parametrize("fit_tier", [None, "", "   ", "unknown"])
def test_judge_prompt_omits_fit_tier_dimension_when_tier_is_not_real(fit_tier):
    system_prompt, user_prompt = build_judge_prompt(
        QUESTIONS,
        ANSWERS,
        ANSWERS,
        {"fit_tier": fit_tier, "segment_label": "Homeowners"},
    )

    assert "fit_tier" not in system_prompt
    assert "across 3 grounding dimensions" in system_prompt
    assert "fit_tier_alignment" not in user_prompt


def test_batch_score_marks_blank_fit_tier_not_applicable_and_excludes_it(monkeypatch):
    judge_outputs = iter(
        [
            {
                "purchase_intent": 1,
                "primary_objection": 1,
                "fit_tier_alignment": 0,
                "use_case_specificity": 1,
            },
            {
                "purchase_intent": 1,
                "primary_objection": 1,
                "fit_tier_alignment": 0,
                "use_case_specificity": 1,
            },
        ]
    )
    monkeypatch.setattr(
        interview_grounding,
        "_call_openrouter",
        lambda *args, **kwargs: json.dumps(next(judge_outputs)),
    )
    pairs = [
        {
            "persona_id": "blank-tier",
            "persona": {"fit_tier": "", "segment_label": "Homeowners"},
            "model_a": {"answers": ANSWERS, "error": None},
            "model_b": {"answers": ANSWERS, "error": None},
        },
        {
            "persona_id": "real-tier",
            "persona": {"fit_tier": "strong", "segment_label": "Homeowners"},
            "model_a": {"answers": ANSWERS, "error": None},
            "model_b": {"answers": ANSWERS, "error": None},
        },
    ]

    report = interview_grounding.score_interview_batch(
        pairs,
        QUESTIONS,
        product=None,
        api_key="test-key",
    )

    blank_score, real_score = report["persona_scores"]
    assert blank_score["dimension_scores"]["fit_tier_alignment"] is None
    assert blank_score["not_applicable_dimensions"] == ["fit_tier_alignment"]
    assert blank_score["score"] == 1.0
    assert real_score["not_applicable_dimensions"] == []
    assert real_score["score"] == 0.75
    assert report["corpus_average"] == 0.875
    assert report["per_dimension_avg"]["fit_tier_alignment"] == 0.0


def test_batch_score_marks_fit_tier_average_not_applicable_when_all_tiers_are_blank(monkeypatch):
    monkeypatch.setattr(
        interview_grounding,
        "_call_openrouter",
        lambda *args, **kwargs: json.dumps(
            {
                "purchase_intent": 1,
                "primary_objection": 1,
                "use_case_specificity": 1,
            }
        ),
    )
    pairs = [
        {
            "persona_id": "blank-tier",
            "persona": {"fit_tier": "", "segment_label": "Homeowners"},
            "model_a": {"answers": ANSWERS, "error": None},
            "model_b": {"answers": ANSWERS, "error": None},
        }
    ]

    report = interview_grounding.score_interview_batch(
        pairs,
        QUESTIONS,
        product=None,
        api_key="test-key",
    )

    assert report["corpus_average"] == 1.0
    assert report["per_dimension_avg"]["fit_tier_alignment"] is None
