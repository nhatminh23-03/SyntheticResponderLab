"""Orchestrate parallel synthetic depth-interview generation via OpenRouter.

STAMP-inspired dual-LLM approach: both models interview every persona so
their responses can be compared for grounding verification. Divergence
is a diagnostic signal, not noise.
"""

from __future__ import annotations

import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from src.simulation.interview_prompt_builder import (
    build_system_prompt,
    build_user_prompt,
    resolve_questions,
)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 3
_MAX_WORKERS = 10

# Default model pair for dual-LLM grounding
DEFAULT_MODEL_A = "openai/gpt-4.1-mini"
DEFAULT_MODEL_B = "google/gemini-2.5-flash"
JUDGE_MODEL = "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_interview_batch(
    personas: list[dict],
    questions: list[dict[str, str]] | None = None,
    model_a: str = DEFAULT_MODEL_A,
    model_b: str = DEFAULT_MODEL_B,
    product: dict | None = None,
    audience: dict | None = None,
    api_key: str = "",
    temperature: float = 0.8,
    max_tokens: int = 3000,
    timeout: int = 90,
) -> list[dict]:
    """Generate one interview pair per persona (both models) in parallel.

    Each persona gets TWO interviews — one from model_a and one from model_b.
    This enables per-persona grounding comparison.

    Returns:
        List of interview pair dicts, one per persona, in original order:
        [
            {
                "persona_id": str,
                "persona_index": int,
                "persona": dict,
                "model_a": {"model": str, "answers": dict, "error": str|None},
                "model_b": {"model": str, "answers": dict, "error": str|None},
            },
            ...
        ]
    """
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    resolved_questions = resolve_questions(questions, product)

    def _interview_one_model(
        persona: dict,
        model: str,
    ) -> dict:
        """Run a single LLM interview against one persona. Returns answers dict."""
        system_prompt = build_system_prompt(persona, product, audience)
        user_prompt = build_user_prompt(resolved_questions)
        raw = _call_openrouter(
            api_key, model, system_prompt, user_prompt, temperature, max_tokens, timeout
        )
        answers = _parse_and_validate(raw, resolved_questions)
        return {"model": model, "answers": answers, "error": None}

    def _generate_pair(index: int, persona: dict) -> dict:
        persona_id = persona.get("persona_id") or f"persona_{index}"
        result: dict = {
            "persona_id": persona_id,
            "persona_index": index,
            "persona": persona,
            "model_a": {"model": model_a, "answers": {}, "error": None},
            "model_b": {"model": model_b, "answers": {}, "error": None},
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Run both models; capture each independently so one failure doesn't kill the pair
        for key, model in [("model_a", model_a), ("model_b", model_b)]:
            try:
                result[key] = _interview_one_model(persona, model)
            except Exception as exc:
                error_answers = {q["id"]: f"[Generation error: {str(exc)[:120]}]" for q in resolved_questions}
                error_answers["additional_thoughts"] = ""
                result[key] = {"model": model, "answers": error_answers, "error": str(exc)[:500]}
        return result

    pairs: list[tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_generate_pair, i, p): i
            for i, p in enumerate(personas)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                pair = future.result()
            except Exception as exc:
                persona = personas[idx]
                persona_id = persona.get("persona_id") or f"persona_{idx}"
                error_answers = {q["id"]: f"[Fatal error: {str(exc)[:120]}]" for q in resolved_questions}
                error_answers["additional_thoughts"] = ""
                pair = {
                    "persona_id": persona_id,
                    "persona_index": idx,
                    "persona": persona,
                    "model_a": {"model": model_a, "answers": error_answers, "error": str(exc)},
                    "model_b": {"model": model_b, "answers": error_answers, "error": str(exc)},
                    "generation_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            pairs.append((idx, pair))

    pairs.sort(key=lambda x: x[0])
    return [p for _, p in pairs]


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
