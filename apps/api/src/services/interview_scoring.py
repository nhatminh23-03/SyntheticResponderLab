"""Transparent, post-interview classification for persisted transcripts."""

from __future__ import annotations

import re
from typing import Any, Final, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import InterviewTurn
from src.services.exceptions import ConflictApiError


POST_INTERVIEW_SCORE_LABEL: Final[str] = "scored after the interview, never before"

_FIT_SIGNALS: Final[tuple[tuple[str, int], ...]] = (
    ("definitely", 3),
    ("absolutely", 3),
    ("ready to buy", 3),
    ("would buy", 3),
    ("want one", 3),
    ("very interested", 3),
    ("really interested", 3),
    ("perfect for", 3),
    ("interested", 1),
    ("appealing", 1),
    ("would consider", 1),
    ("could see", 1),
    ("curious", 1),
    ("useful", 1),
    ("not interested", -4),
    ("no interest", -4),
    ("would not buy", -4),
    ("wouldn't buy", -4),
    ("not for me", -4),
    ("deal breaker", -3),
    ("cannot justify", -3),
    ("can't justify", -3),
    ("too expensive", -2),
    ("unsure", -1),
    ("uncertain", -1),
    ("hesitant", -1),
    ("depends", -1),
)

_POSITIVE_EMOTION_SIGNALS: Final[tuple[str, ...]] = (
    "excited",
    "enthusiastic",
    "happy",
    "love",
    "appealing",
    "optimistic",
    "interested",
    "useful",
)

_NEGATIVE_EMOTION_SIGNALS: Final[tuple[tuple[str, int], ...]] = (
    ("frustrated", 1),
    ("anxious", 1),
    ("worried", 1),
    ("worry", 1),
    ("skeptical", 1),
    ("disappointed", 1),
    ("dislike", 1),
    ("hate", 1),
    ("concerned", 1),
    ("concern", 1),
    ("nervous", 1),
    ("uncomfortable", 1),
    ("not interested", 2),
)


def _signal_polarity(text: str, phrase: str) -> tuple[bool, bool]:
    """Return whether a signal occurs affirmatively and under direct negation."""
    affirmative = False
    negated = False
    for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
        # Negation should not leak across sentences or contrastive clauses. Three
        # preceding tokens covers ordinary forms such as "not very interested",
        # "not at all useful", and "wouldn't be excited".
        clause = re.split(
            r"[.!?;:\n]|\b(?:but|however|though|although|yet)\b",
            text[:match.start()],
        )[-1]
        preceding_tokens = re.findall(r"[a-z]+(?:['’][a-z]+)?", clause)[-3:]
        negation_indexes = []
        for index, token in enumerate(preceding_tokens):
            if (
                token in {"not", "never", "cannot", "hardly", "barely"}
                or token.endswith("n't")
                or (
                    token == "no"
                    and preceding_tokens[index + 1:index + 2] == ["longer"]
                )
            ):
                negation_indexes.append(index)
        is_negated = any(
            "only" not in preceding_tokens[index + 1:]
            for index in negation_indexes
        )
        if is_negated:
            negated = True
        else:
            affirmative = True
    return affirmative, negated


def classify_interview_transcript(
    transcript: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Classify interviewee language only after at least one answer exists."""
    answers = [
        str(turn.get("content") or turn.get("text") or "").strip().lower()
        for turn in transcript
        if str(turn.get("role") or "").strip() == "assistant"
        and str(turn.get("content") or turn.get("text") or "").strip()
    ]
    if not answers:
        raise ValueError("Post-interview scoring requires a completed transcript answer.")

    answer_text = "\n".join(answers)
    fit_score = 0
    for phrase, weight in _FIT_SIGNALS:
        affirmative, negated = _signal_polarity(answer_text, phrase)
        if affirmative:
            fit_score += weight
        # Negating a positive purchase-intent signal is negative evidence. A
        # negated negative signal is only omitted because it does not necessarily
        # express positive purchase intent (for example, "not concerned").
        if negated and weight > 0:
            fit_score -= weight
    if fit_score >= 3:
        fit_tier = "strong"
    elif fit_score >= 1:
        fit_tier = "soft"
    elif fit_score >= -1:
        fit_tier = "latent"
    else:
        fit_tier = "edge"

    positive_score = 0
    negative_score = 0
    for phrase in _POSITIVE_EMOTION_SIGNALS:
        affirmative, negated = _signal_polarity(answer_text, phrase)
        positive_score += int(affirmative)
        negative_score += int(negated)
    for phrase, weight in _NEGATIVE_EMOTION_SIGNALS:
        affirmative, _ = _signal_polarity(answer_text, phrase)
        if affirmative:
            negative_score += weight
    if positive_score > negative_score:
        emotional_classification = "positive"
    elif negative_score > positive_score:
        emotional_classification = "negative"
    else:
        emotional_classification = "neutral"

    return {
        "fit_tier": fit_tier,
        "emotional_classification": emotional_classification,
        "label": POST_INTERVIEW_SCORE_LABEL,
    }


def score_persisted_interview_transcript(
    session: Session,
    *,
    study_id: Any,
    persona_id: str,
    session_id: str,
    model: str,
) -> dict[str, str]:
    """Load and score a transcript only after its assistant turn is persisted."""
    turns = session.scalars(
        select(InterviewTurn)
        .where(
            InterviewTurn.study_id == study_id,
            InterviewTurn.persona_id == persona_id,
            InterviewTurn.session_id == session_id,
            InterviewTurn.model == model,
        )
        .order_by(InterviewTurn.created_at, InterviewTurn.id)
    ).all()
    try:
        return classify_interview_transcript(
            [{"role": turn.role, "content": turn.text} for turn in turns]
        )
    except ValueError as exc:
        raise ConflictApiError(
            "Post-interview scoring requires a persisted transcript answer."
        ) from exc
