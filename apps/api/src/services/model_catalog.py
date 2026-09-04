"""Curated, price-aware model catalog for classroom interview runs."""

from __future__ import annotations

from decimal import Decimal
from typing import Final


PRICING_AS_OF: Final[str] = "2026-09-04"
PRICING_SOURCE: Final[str] = "https://openrouter.ai/api/v1/models"
TIER_ORDER: Final[tuple[str, ...]] = ("cheap", "mid", "expensive")
MIN_INTERVIEW_PERSONAS: Final[int] = 3
DEFAULT_INTERVIEW_PERSONAS: Final[int] = 3
MAX_INTERVIEW_PERSONAS: Final[int] = 30

# Planning allowance for one model's side of one AI-to-AI persona interview.
# The estimate is intentionally explicit so the UI can distinguish it from the
# measured provider usage that is persisted after a call.
ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA: Final[int] = 10_000
ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA: Final[int] = 2_000
_TOKENS_PER_MILLION: Final[Decimal] = Decimal("1000000")

# OpenRouter prices in USD per one million text tokens. Keep this list small and
# deliberate: these are the choices students compare, not the provider's entire
# catalog. Within and across tiers, entries are ordered from cheapest to most
# expensive on both prompt and completion prices.
MODEL_TIERS: Final[dict[str, tuple[dict[str, object], ...]]] = {
    "cheap": (
        {
            "id": "google/gemini-2.5-flash-lite",
            "name": "Gemini 2.5 Flash Lite",
            "tier": "cheap",
            "prompt_price_per_million": 0.10,
            "completion_price_per_million": 0.40,
        },
        {
            "id": "openai/gpt-4o-mini",
            "name": "GPT-4o mini",
            "tier": "cheap",
            "prompt_price_per_million": 0.15,
            "completion_price_per_million": 0.60,
        },
    ),
    "mid": (
        {
            "id": "google/gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "tier": "mid",
            "prompt_price_per_million": 0.30,
            "completion_price_per_million": 2.50,
        },
        {
            "id": "anthropic/claude-haiku-4.5",
            "name": "Claude Haiku 4.5",
            "tier": "mid",
            "prompt_price_per_million": 1.00,
            "completion_price_per_million": 5.00,
        },
    ),
    "expensive": (
        {
            "id": "google/gemini-2.5-pro",
            "name": "Gemini 2.5 Pro",
            "tier": "expensive",
            "prompt_price_per_million": 1.25,
            "completion_price_per_million": 10.00,
        },
        {
            "id": "anthropic/claude-sonnet-4.5",
            "name": "Claude Sonnet 4.5",
            "tier": "expensive",
            "prompt_price_per_million": 3.00,
            "completion_price_per_million": 15.00,
        },
    ),
}

DEFAULT_INTERVIEW_MODEL_ID: Final[str] = str(MODEL_TIERS["cheap"][0]["id"])


def _estimated_cost_per_persona_usd(model: dict[str, object]) -> float:
    prompt_cost = (
        Decimal(str(model["prompt_price_per_million"]))
        * ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA
    )
    completion_cost = (
        Decimal(str(model["completion_price_per_million"]))
        * ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA
    )
    return float((prompt_cost + completion_cost) / _TOKENS_PER_MILLION)


def list_interview_model_catalog() -> dict[str, object]:
    """Return a JSON-ready catalog in cheapest-first tier order."""
    models = []
    for tier in TIER_ORDER:
        for source in MODEL_TIERS[tier]:
            model = dict(source)
            model["estimated_cost_per_persona_usd"] = _estimated_cost_per_persona_usd(source)
            models.append(model)
    return {
        "source": "curated",
        "pricing_as_of": PRICING_AS_OF,
        "pricing_source": PRICING_SOURCE,
        "default_model_id": DEFAULT_INTERVIEW_MODEL_ID,
        "persona_count": {
            "minimum": MIN_INTERVIEW_PERSONAS,
            "default": DEFAULT_INTERVIEW_PERSONAS,
            "maximum": MAX_INTERVIEW_PERSONAS,
        },
        "cost_estimate": {
            "prompt_tokens_per_model_persona": ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA,
            "completion_tokens_per_model_persona": ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA,
        },
        "models": models,
    }
