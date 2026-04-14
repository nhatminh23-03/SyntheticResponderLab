"""STAMP-inspired grounding scorer for dual-LLM interview pairs.

Computes per-persona agreement scores across four dimensions, then
aggregates to a corpus-level average analogous to Krippendorff's α.

Threshold: corpus_average >= 0.67 → batch passes; below → flag for review.
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Any

import requests

from src.simulation.interview_prompt_builder import (
    build_judge_prompt,
    resolve_questions,
)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 3
_DIMENSIONS = ["purchase_intent", "primary_objection", "fit_tier_alignment", "use_case_specificity"]
GROUNDING_THRESHOLD = 0.67


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def score_interview_batch(
    pairs: list[dict],
    questions: list[dict[str, str]] | None,
    product: dict | None,
    api_key: str,
    judge_model: str = "openai/gpt-4o-mini",
    timeout: int = 60,
) -> dict:
    """Score all interview pairs and return a corpus-level grounding report.

    Args:
        pairs:        Output from interview_runner.run_interview_batch().
        questions:    Same question list used during interview generation.
        product:      Product dict for placeholder resolution.
        api_key:      OpenRouter API key.
        judge_model:  Model to use as judge (should be different from A/B).
        timeout:      Per-request timeout.

    Returns:
        {
            "corpus_average": float,
            "passes_threshold": bool,
            "threshold": float,
            "per_dimension_avg": {dimension: float, ...},
            "flagged_persona_ids": [str, ...],
            "persona_scores": [
                {
                    "persona_id": str,
                    "score": float,
                    "dimension_scores": {dimension: 0|1, ...},
                    "has_error": bool,
                },
                ...
            ],
        }
    """
    resolved_questions = resolve_questions(questions, product)
    persona_scores = []

    for pair in pairs:
        persona_id = pair.get("persona_id", "unknown")
        persona = pair.get("persona", {})
        answers_a = pair.get("model_a", {}).get("answers", {})
        answers_b = pair.get("model_b", {}).get("answers", {})
        has_error = bool(
            pair.get("model_a", {}).get("error")
            or pair.get("model_b", {}).get("error")
        )

        if has_error:
            # Error pairs contribute 0 to all dimensions
            dimension_scores = {d: 0 for d in _DIMENSIONS}
            score = 0.0
        else:
            dimension_scores = _score_pair(
                resolved_questions, answers_a, answers_b, persona,
                api_key, judge_model, timeout
            )
            score = sum(dimension_scores.values()) / len(_DIMENSIONS)

        persona_scores.append({
            "persona_id": persona_id,
            "score": round(score, 4),
            "dimension_scores": dimension_scores,
            "has_error": has_error,
        })

    if not persona_scores:
        return {
            "corpus_average": 0.0,
            "passes_threshold": False,
            "threshold": GROUNDING_THRESHOLD,
            "per_dimension_avg": {d: 0.0 for d in _DIMENSIONS},
            "flagged_persona_ids": [],
            "persona_scores": [],
        }

    corpus_average = sum(p["score"] for p in persona_scores) / len(persona_scores)

    per_dimension_avg = {
        d: round(
            sum(p["dimension_scores"].get(d, 0) for p in persona_scores) / len(persona_scores),
            4,
        )
        for d in _DIMENSIONS
    }

    flagged = [
        p["persona_id"] for p in persona_scores
        if p["score"] < GROUNDING_THRESHOLD
    ]

    return {
        "corpus_average": round(corpus_average, 4),
        "passes_threshold": corpus_average >= GROUNDING_THRESHOLD,
        "threshold": GROUNDING_THRESHOLD,
        "per_dimension_avg": per_dimension_avg,
        "flagged_persona_ids": flagged,
        "persona_scores": persona_scores,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _score_pair(
    questions: list[dict[str, str]],
    answers_a: dict[str, str],
    answers_b: dict[str, str],
    persona: dict,
    api_key: str,
    judge_model: str,
    timeout: int,
) -> dict[str, int]:
    """Call the judge LLM to score one persona pair. Returns {dimension: 0|1}."""
    system_prompt, user_prompt = build_judge_prompt(questions, answers_a, answers_b, persona)

    raw = _call_openrouter(api_key, judge_model, system_prompt, user_prompt, timeout)
    return _parse_dimension_scores(raw)


def _parse_dimension_scores(raw: str) -> dict[str, int]:
    """Parse judge output and return {dimension: 0|1}. Defaults to 0 on parse failure."""
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

    result = {}
    for d in _DIMENSIONS:
        val = parsed.get(d, 0)
        try:
            result[d] = 1 if int(val) >= 1 else 0
        except (TypeError, ValueError):
            result[d] = 0
    return result


def _call_openrouter(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }
    if model.startswith("openai/"):
        body["response_format"] = {"type": "json_object"}

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(_OPENROUTER_URL, headers=headers, json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = min(65, (2 ** attempt) + random.uniform(0, 1))
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Judge LLM call failed after {_MAX_RETRIES} attempts: {exc}"
                ) from exc

    raise RuntimeError("Exhausted retries.")
