"""Orchestrate parallel synthetic depth-interview generation via OpenRouter."""

from __future__ import annotations

import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import requests

from backend.schemas import InterviewTranscript
from backend.simulation.interview_prompt_builder import (
    build_system_prompt,
    build_user_prompt,
    resolve_questions,
)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 3
_MAX_WORKERS = 10


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_interviews(
    personas: list[Any],
    questions: list[dict[str, str]] | None = None,
    model_a: str = "openai/gpt-4.1-mini",
    model_b: str = "google/gemini-2.5-flash",
    bpc: Any | None = None,
    audience: Any | None = None,
    temperature: float = 0.8,
    max_tokens: int = 3000,
    timeout: int = 90,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[InterviewTranscript]:
    """Generate one interview per persona in parallel.

    Personas are interleaved across model_a and model_b (even index → model_a,
    odd index → model_b), matching the prototype's MODEL_ASSIGNMENTS approach.

    Args:
        personas:          List of PersonaProfile objects.
        questions:         List of {"id": ..., "text": ...} dicts, or None to use defaults.
        model_a:           First OpenRouter model ID.
        model_b:           Second OpenRouter model ID.
        bpc:               BusinessProductContext for prompt grounding.
        audience:          AudienceFilter for location/lifestyle context.
        temperature:       LLM temperature (0.8 for creative interview responses).
        max_tokens:        Max tokens per response.
        timeout:           Per-request timeout in seconds.
        progress_callback: Optional callable(completed_count, total_count).

    Returns:
        List of InterviewTranscript objects (one per persona).
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    resolved_questions = resolve_questions(questions, bpc)
    total = len(personas)
    completed_count = 0

    def _generate_one(index: int, persona: Any) -> InterviewTranscript:
        model = model_a if index % 2 == 0 else model_b
        system_prompt = build_system_prompt(persona, bpc, audience)
        user_prompt = build_user_prompt(resolved_questions)
        raw = _call_openrouter(api_key, model, system_prompt, user_prompt, temperature, max_tokens, timeout)
        parsed = _parse_and_validate(raw, resolved_questions)
        return _build_transcript(persona, model, parsed, resolved_questions)

    results: list[tuple[int, InterviewTranscript]] = []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_generate_one, i, persona): i
            for i, persona in enumerate(personas)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                transcript = future.result()
            except Exception as exc:
                # Build a fallback transcript so one failure doesn't abort the run
                persona = personas[idx]
                model = model_a if idx % 2 == 0 else model_b
                transcript = _build_error_transcript(persona, model, str(exc), resolved_questions)
            results.append((idx, transcript))
            completed_count += 1
            if progress_callback:
                progress_callback(completed_count, total)

    # Return in original persona order
    results.sort(key=lambda x: x[0])
    return [t for _, t in results]


# ---------------------------------------------------------------------------
# OpenRouter call
# ---------------------------------------------------------------------------

def _call_openrouter(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
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
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # GPT models support response_format JSON mode
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
                    f"OpenRouter call failed after {_MAX_RETRIES} attempts (model={model}): {exc}"
                ) from exc

    raise RuntimeError("Exhausted retries.")


# ---------------------------------------------------------------------------
# Parse and validate
# ---------------------------------------------------------------------------

def _parse_and_validate(raw: str, questions: list[dict[str, str]]) -> dict[str, str]:
    """Parse JSON response and fill missing question keys with a placeholder."""
    parsed: dict[str, Any] = {}

    # Try direct parse
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Strip markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Extract first {...} block
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

    # Ensure every question has an answer; coerce to str; enforce min length
    result: dict[str, str] = {}
    for q in questions:
        qid = q["id"]
        answer = parsed.get(qid, "")
        answer = str(answer).strip() if answer else ""
        if len(answer) < 20:
            answer = "[No response provided]"
        result[qid] = answer

    result["additional_thoughts"] = str(parsed.get("additional_thoughts", "")).strip()
    return result


# ---------------------------------------------------------------------------
# Transcript builders
# ---------------------------------------------------------------------------

def _build_transcript(
    persona: Any,
    model: str,
    answers: dict[str, str],
    questions: list[dict[str, str]],
) -> InterviewTranscript:
    persona_id = getattr(persona, "persona_id", "unknown")
    interview_id = f"{persona_id}_{model.split('/')[-1].replace('-', '_')}"
    timestamp = datetime.now(timezone.utc).isoformat()

    return InterviewTranscript(
        interview_id=interview_id,
        persona_id=persona_id,
        model=model,
        age_bucket=getattr(persona, "age_bucket", None),
        income_bucket=getattr(persona, "income_bucket", None),
        ownership=getattr(persona, "ownership", None),
        work_mode=getattr(persona, "work_mode", None),
        home_type=getattr(persona, "home_type", None),
        segment_label=getattr(persona, "segment_label", None),
        lifestyle_tags=list(getattr(persona, "lifestyle_tags", []) or []),
        affordability_pressure=getattr(persona, "affordability_pressure", None),
        fit_tier=getattr(persona, "fit_tier", None),
        awareness_stage=getattr(persona, "awareness_stage", None),
        answers=answers,
        generation_timestamp=timestamp,
    )


def _build_error_transcript(
    persona: Any,
    model: str,
    error: str,
    questions: list[dict[str, str]],
) -> InterviewTranscript:
    error_answers = {q["id"]: f"[Generation error: {error[:120]}]" for q in questions}
    error_answers["additional_thoughts"] = ""
    return _build_transcript(persona, model, error_answers, questions)
