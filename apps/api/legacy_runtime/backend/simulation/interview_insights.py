"""Chatbot backend for interview insights analysis.

Injects ResearchBrief + BusinessProductContext + filtered interview transcripts
as a system prompt, then wraps OpenRouter or Anthropic for conversational Q&A.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Optional

import requests

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 3


def build_chatbot_system_prompt(
    research_brief: Any,
    bpc: Any | None,
    transcripts: list[Any],
    focus_tiers: list[str] | None = None,
    focus_segments: list[str] | None = None,
) -> str:
    """Build the system prompt injecting context and filtered transcripts.

    Args:
        research_brief:  ResearchBrief object.
        bpc:             BusinessProductContext object (optional).
        transcripts:     List of InterviewTranscript objects.
        focus_tiers:     Fit tiers to include; None means all.
        focus_segments:  Segment labels to include; None means all.

    Returns:
        System prompt string.
    """
    # --- Filter transcripts ---
    filtered = transcripts
    if focus_tiers:
        filtered = [t for t in filtered if getattr(t, "fit_tier", None) in focus_tiers]
    if focus_segments:
        filtered = [
            t for t in filtered
            if getattr(t, "segment_label", None) in focus_segments
        ]

    # --- Research brief section ---
    brief_lines = ["## Research Brief"]
    primary_q = getattr(research_brief, "primary_question", None)
    if primary_q:
        brief_lines.append(f"**Primary Question:** {primary_q}")

    hypotheses = getattr(research_brief, "hypotheses", []) or []
    if hypotheses:
        brief_lines.append("**Hypotheses:**")
        for h in hypotheses:
            brief_lines.append(f"- {h}")

    decisions = getattr(research_brief, "decisions_to_inform", []) or []
    if decisions:
        brief_lines.append("**Decisions to Inform:**")
        for d in decisions:
            brief_lines.append(f"- {d}")

    known = getattr(research_brief, "known_context", None)
    if known:
        brief_lines.append(f"**Known Context:** {known}")

    notes = getattr(research_brief, "notes", None)
    if notes:
        brief_lines.append(f"**Notes:** {notes}")

    # --- BPC section ---
    bpc_lines = []
    if bpc:
        bpc_lines.append("## Product Context")
        product_name = getattr(bpc, "product_name", None)
        product_desc = getattr(bpc, "product_description", None)
        if product_name:
            bpc_lines.append(f"**Product:** {product_name}")
        if product_desc:
            bpc_lines.append(f"**Description:** {product_desc}")
        primary_goal = getattr(bpc, "primary_goal", None)
        if primary_goal:
            bpc_lines.append(f"**Primary Goal:** {primary_goal}")

    # --- Transcripts section ---
    transcript_lines = [f"## Interview Transcripts ({len(filtered)} included)"]
    if not filtered:
        transcript_lines.append("No transcripts match the current filters.")
    else:
        for i, t in enumerate(filtered, 1):
            header = (
                f"### Interview {i} — {getattr(t, 'persona_id', 'unknown')} "
                f"| fit_tier={getattr(t, 'fit_tier', '?')} "
                f"| segment={getattr(t, 'segment_label', '?')} "
                f"| model={getattr(t, 'model', '?').split('/')[-1]}"
            )
            transcript_lines.append(header)
            answers: dict = getattr(t, "answers", {}) or {}
            for qid, answer in answers.items():
                if qid == "additional_thoughts":
                    continue
                transcript_lines.append(f"**{qid}:** {answer}")
            extra = answers.get("additional_thoughts", "")
            if extra:
                transcript_lines.append(f"**Additional thoughts:** {extra}")
            transcript_lines.append("")

    parts = [
        "You are a qualitative research analyst. Your job is to help the researcher "
        "interpret synthetic depth-interview transcripts in the context of their research brief.",
        "",
        "Answer questions concisely and ground every claim in specific transcript evidence. "
        "Cite persona IDs or interview numbers when referencing specific responses. "
        "Flag when evidence is thin or when transcripts conflict.",
        "",
        "\n".join(brief_lines),
        "",
        "\n".join(bpc_lines) if bpc_lines else "",
        "",
        "\n".join(transcript_lines),
    ]
    return "\n".join(p for p in parts if p is not None).strip()


def call_chatbot(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    timeout: int = 60,
) -> str:
    """Call OpenRouter with a full message history and return the assistant reply.

    Args:
        messages:    Full chat history including the system message as first entry.
        model:       OpenRouter model ID.
        api_key:     OpenRouter API key.
        max_tokens:  Max tokens for the response.
        temperature: Sampling temperature (low for analytical tasks).
        timeout:     Request timeout in seconds.

    Returns:
        Assistant reply string.

    Raises:
        RuntimeError: After all retries are exhausted.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

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


def call_chatbot_anthropic(
    system_prompt: str,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> str:
    """Call the Anthropic API directly for chatbot responses.

    Args:
        system_prompt: The system context string (injected separately per Anthropic API).
        messages:      Conversation history — list of {"role": ..., "content": ...} dicts,
                       excluding the system message.
        model:         Anthropic model ID (e.g. "claude-haiku-4-5-20251001").
        api_key:       Anthropic API key.
        max_tokens:    Max tokens for the response.
        temperature:   Sampling temperature.

    Returns:
        Assistant reply string.

    Raises:
        RuntimeError: After all retries are exhausted.
    """
    try:
        import anthropic as _anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package is not installed. Run: pip install anthropic>=0.50.0"
        ) from exc

    client = _anthropic.Anthropic(api_key=api_key)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            )
            return response.content[0].text
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = min(65, (2 ** attempt) + random.uniform(0, 1))
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Anthropic call failed after {_MAX_RETRIES} attempts (model={model}): {exc}"
                ) from exc

    raise RuntimeError("Exhausted retries.")


def resolve_chatbot_backend() -> tuple[str, str]:
    """Return (backend, api_key) for the first available key.

    Checks OPENROUTER_API_KEY first, then ANTHROPIC_API_KEY.

    Returns:
        ("openrouter", key) or ("anthropic", key)

    Raises:
        RuntimeError: If neither key is set.
    """
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if or_key:
        return ("openrouter", or_key)

    ant_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if ant_key:
        return ("anthropic", ant_key)

    raise RuntimeError(
        "No API key found. Set OPENROUTER_API_KEY or ANTHROPIC_API_KEY in your .env file."
    )
