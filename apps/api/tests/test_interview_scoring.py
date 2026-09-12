from __future__ import annotations

from decimal import Decimal

import pytest

from src.persistence.models import InterviewTurn, Persona, Study
from src.persistence.persona_seed import load_persona_seed_rows
from src.services.exceptions import ConflictApiError
from src.services.interview_scoring import (
    POST_INTERVIEW_SCORE_LABEL,
    classify_interview_transcript,
    score_persisted_interview_transcript,
)


@pytest.mark.parametrize(
    ("answer", "fit_tier", "emotion"),
    [
        ("I am excited and would definitely want one.", "strong", "positive"),
        ("It seems useful and I would consider it.", "soft", "positive"),
        ("I need the dimensions before deciding.", "latent", "neutral"),
        ("I am skeptical and it is too expensive, so it is not for me.", "edge", "negative"),
    ],
)
def test_classifies_fit_and_emotion_codebook_branches(answer, fit_tier, emotion):
    score = classify_interview_transcript(
        [{"role": "user", "content": "I am excited and would definitely buy it."},
         {"role": "assistant", "content": answer}]
    )

    assert score == {
        "fit_tier": fit_tier,
        "emotional_classification": emotion,
        "label": POST_INTERVIEW_SCORE_LABEL,
    }


def test_emotion_tie_is_neutral():
    score = classify_interview_transcript(
        [{"role": "assistant", "content": "It is appealing, but I am concerned."}]
    )

    assert score["emotional_classification"] == "neutral"


def test_negated_interest_and_emotion_are_not_scored_as_positive():
    score = classify_interview_transcript(
        [{
            "role": "assistant",
            "content": "I am not very interested, and I am not excited about it.",
        }]
    )

    assert score["fit_tier"] == "edge"
    assert score["emotional_classification"] == "negative"


def test_negated_negative_emotions_are_not_scored_as_negative():
    score = classify_interview_transcript(
        [{
            "role": "assistant",
            "content": "I am not concerned, and I am not worried about the price.",
        }]
    )

    assert score["emotional_classification"] == "neutral"


def test_positive_no_doubt_idiom_is_not_mistaken_for_negation():
    score = classify_interview_transcript(
        [{
            "role": "assistant",
            "content": "I have no doubt I would buy it. I am excited about it.",
        }]
    )

    assert score["fit_tier"] == "strong"
    assert score["emotional_classification"] == "positive"


def test_scoring_rejects_a_transcript_without_an_interviewee_answer():
    with pytest.raises(ValueError, match="completed transcript answer"):
        classify_interview_transcript(
            [{"role": "user", "content": "Would you buy it?"}]
        )


def test_persisted_scoring_requires_then_uses_the_saved_answer(db_session):
    persona_row = load_persona_seed_rows()[0]
    study = Study(
        public_id="study-score",
        lifecycle_status="draft",
    )
    db_session.add_all([Persona(**persona_row), study])
    db_session.flush()

    with pytest.raises(ConflictApiError, match="persisted transcript answer"):
        score_persisted_interview_transcript(
            db_session,
            study_id=study.id,
            persona_id=persona_row["persona_id"],
            session_id="session-score",
            model="provider/model",
        )

    db_session.add(
        InterviewTurn(
            study_id=study.id,
            persona_id=persona_row["persona_id"],
            session_id="session-score",
            role="assistant",
            text="I am excited and very interested.",
            model="provider/model",
            tokens_in=10,
            tokens_out=5,
            cost_usd=Decimal("0"),
        )
    )
    db_session.flush()

    score = score_persisted_interview_transcript(
        db_session,
        study_id=study.id,
        persona_id=persona_row["persona_id"],
        session_id="session-score",
        model="provider/model",
    )

    assert score["fit_tier"] == "strong"
    assert score["emotional_classification"] == "positive"
