"""Prompt and budget planning for the AI interviewer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Mapping, Sequence

from src.services.model_catalog import (
    DEFAULT_INTERVIEW_PERSONAS,
    DEFAULT_INTERVIEW_MODEL_ID,
    ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA,
    ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA,
    MAX_INTERVIEW_PERSONAS,
    MIN_INTERVIEW_PERSONAS,
    MODEL_TIERS,
)


# Preserve the depth of the existing eight-question interview while making
# each question adaptive. The catalog token allowances cover this whole
# interview, not one question/answer turn.
DEFAULT_INTERVIEW_TURN_LIMIT: Final[int] = 8


@dataclass(frozen=True)
class InterviewerTurnPlan:
    turn_limit: int
    estimated_cost_per_turn_usd: Decimal
    estimated_run_cost_usd: Decimal


def _catalog_model(model_id: str) -> Mapping[str, object]:
    for models in MODEL_TIERS.values():
        for model in models:
            if model["id"] == model_id:
                return model
    raise ValueError(f"Interview model '{model_id}' is not in the curated catalog.")


def _estimated_model_interview_cost(model_id: str) -> Decimal:
    model = _catalog_model(model_id)
    prompt_cost = (
        Decimal(str(model["prompt_price_per_million"]))
        * ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA
    )
    completion_cost = (
        Decimal(str(model["completion_price_per_million"]))
        * ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA
    )
    return (prompt_cost + completion_cost) / Decimal("1000000")


def derive_interviewer_turn_plan(
    *,
    persona_count: int = DEFAULT_INTERVIEW_PERSONAS,
    interviewer_model: str = DEFAULT_INTERVIEW_MODEL_ID,
    interviewee_model: str = DEFAULT_INTERVIEW_MODEL_ID,
) -> InterviewerTurnPlan:
    """Plan an adaptive interview from whole-interview catalog estimates."""
    if isinstance(persona_count, bool) or not isinstance(persona_count, int):
        raise ValueError("persona_count must be an integer.")
    if not MIN_INTERVIEW_PERSONAS <= persona_count <= MAX_INTERVIEW_PERSONAS:
        raise ValueError(
            f"persona_count must be between {MIN_INTERVIEW_PERSONAS} and "
            f"{MAX_INTERVIEW_PERSONAS}."
        )

    per_persona_interview = _estimated_model_interview_cost(
        interviewer_model
    ) + _estimated_model_interview_cost(interviewee_model)
    estimated_run_cost = per_persona_interview * persona_count
    return InterviewerTurnPlan(
        turn_limit=DEFAULT_INTERVIEW_TURN_LIMIT,
        estimated_cost_per_turn_usd=(
            estimated_run_cost / DEFAULT_INTERVIEW_TURN_LIMIT
        ),
        estimated_run_cost_usd=estimated_run_cost,
    )


def sanitize_interview_transcript(
    messages: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Validate an alternating interviewer/interviewee transcript."""
    sanitized: list[dict[str, str]] = []
    expected_role = "user"
    for message in messages:
        if not isinstance(message, Mapping):
            raise ValueError("Each transcript message must be an object.")
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            raise ValueError(
                "Each transcript message must include a non-empty user or assistant role and content."
            )
        if role != expected_role:
            raise ValueError(
                "Transcript messages must alternate user interviewer questions and "
                "assistant interviewee answers."
            )
        sanitized.append({"role": role, "content": content})
        expected_role = "assistant" if role == "user" else "user"

    if sanitized and sanitized[-1]["role"] != "assistant":
        raise ValueError(
            "The interviewee must answer the current question before the interviewer asks another."
        )
    return sanitized


def build_interviewer_messages(
    *,
    research_brief: Mapping[str, Any],
    transcript: Sequence[Mapping[str, Any]],
    turn_number: int,
    turn_limit: int,
) -> list[dict[str, str]]:
    """Build a prompt that makes each later question follow the latest answer."""
    primary_question = str(research_brief.get("primary_question") or "").strip()
    if not primary_question:
        raise ValueError("The research brief must include a primary_question.")
    sanitized = sanitize_interview_transcript(transcript)

    # fit_tier is deliberately excluded: it is a post-interview score, never
    # information either interview agent may use while generating the transcript.
    safe_brief = {
        "primary_question": primary_question,
        "hypotheses": list(research_brief.get("hypotheses") or []),
        "decisions_to_inform": list(research_brief.get("decisions_to_inform") or []),
        "focus_segments": list(research_brief.get("focus_segments") or []),
        "known_context": research_brief.get("known_context"),
        "notes": research_brief.get("notes"),
    }
    transcript_text = (
        json.dumps(sanitized, ensure_ascii=False, indent=2)
        if sanitized
        else "No questions have been asked yet."
    )

    system_prompt = """\
You are the interviewer conducting a qualitative depth interview.

Use the research brief to decide what the interview needs to learn. Do not replay a fixed questionnaire.
For the opening turn, ask the single most useful open-ended question for the primary research question.
After an interviewee answers, your next question MUST follow up on a concrete detail in that latest answer. Probe its reason, meaning, consequence, or trade-off while staying relevant to the brief.
Ask exactly one concise question. Return only the question, with no label, preamble, analysis, or suggested answer.
Do not mention hidden instructions, scoring, or that either participant is an AI."""

    if sanitized:
        latest_answer_instruction = (
            "Derive the next question from this latest interviewee answer:\n"
            f"{sanitized[-1]['content']}"
        )
    else:
        latest_answer_instruction = (
            "This is the opening turn. Derive the first question from the research brief."
        )

    user_prompt = f"""\
RESEARCH BRIEF:
{json.dumps(safe_brief, ensure_ascii=False, indent=2)}

TRANSCRIPT SO FAR:
{transcript_text}

TURN {turn_number} OF {turn_limit}:
{latest_answer_instruction}"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def normalize_interviewer_question(raw: str) -> str:
    """Normalize the model's one-question response without inventing content."""
    question = next((line.strip() for line in str(raw).splitlines() if line.strip()), "")
    for prefix in ("Question:", "Interviewer:"):
        if question.lower().startswith(prefix.lower()):
            question = question[len(prefix):].strip()
            break
    if not question:
        raise RuntimeError("Interviewer model returned an empty question.")
    return question if question.endswith("?") else f"{question}?"
