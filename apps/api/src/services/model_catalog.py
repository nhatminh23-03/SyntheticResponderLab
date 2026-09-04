"""Curated, price-aware model catalog for classroom interview runs."""

from __future__ import annotations

from typing import Final


PRICING_AS_OF: Final[str] = "2026-09-04"
PRICING_SOURCE: Final[str] = "https://openrouter.ai/api/v1/models"
TIER_ORDER: Final[tuple[str, ...]] = ("cheap", "mid", "expensive")

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


def list_interview_model_catalog() -> dict[str, object]:
    """Return a JSON-ready catalog in cheapest-first tier order."""
    models = [dict(model) for tier in TIER_ORDER for model in MODEL_TIERS[tier]]
    return {
        "source": "curated",
        "pricing_as_of": PRICING_AS_OF,
        "pricing_source": PRICING_SOURCE,
        "default_model_id": DEFAULT_INTERVIEW_MODEL_ID,
        "models": models,
    }
