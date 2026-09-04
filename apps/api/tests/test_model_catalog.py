from __future__ import annotations

from decimal import Decimal

from src.services.model_catalog import (
    DEFAULT_INTERVIEW_PERSONAS,
    DEFAULT_INTERVIEW_MODEL_ID,
    ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA,
    ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA,
    MAX_INTERVIEW_PERSONAS,
    MIN_INTERVIEW_PERSONAS,
    MODEL_TIERS,
    PRICING_AS_OF,
    PRICING_SOURCE,
    TIER_ORDER,
    list_interview_model_catalog,
)


def test_model_tiers_are_complete_real_prices_and_cheapest_first():
    assert tuple(MODEL_TIERS) == TIER_ORDER == ("cheap", "mid", "expensive")

    models = [model for tier in TIER_ORDER for model in MODEL_TIERS[tier]]
    assert models
    assert DEFAULT_INTERVIEW_MODEL_ID == models[0]["id"]
    assert all(model["tier"] in TIER_ORDER for model in models)
    assert all(model["prompt_price_per_million"] > 0 for model in models)
    assert all(model["completion_price_per_million"] > 0 for model in models)
    assert [model["prompt_price_per_million"] for model in models] == sorted(
        model["prompt_price_per_million"] for model in models
    )
    assert [model["completion_price_per_million"] for model in models] == sorted(
        model["completion_price_per_million"] for model in models
    )


def test_interview_model_catalog_is_json_ready_and_preserves_tiers():
    catalog = list_interview_model_catalog()

    assert catalog["source"] == "curated"
    assert catalog["pricing_as_of"] == PRICING_AS_OF
    assert catalog["pricing_source"] == PRICING_SOURCE
    assert catalog["default_model_id"] == DEFAULT_INTERVIEW_MODEL_ID
    assert catalog["persona_count"] == {
        "minimum": 3,
        "default": 3,
        "maximum": 30,
    }
    assert catalog["cost_estimate"] == {
        "prompt_tokens_per_model_persona": 10_000,
        "completion_tokens_per_model_persona": 2_000,
    }
    assert [model["tier"] for model in catalog["models"]] == [
        "cheap",
        "cheap",
        "mid",
        "mid",
        "expensive",
        "expensive",
    ]


def test_persona_count_bounds_and_default_match_the_classroom_run_contract():
    assert MIN_INTERVIEW_PERSONAS == DEFAULT_INTERVIEW_PERSONAS == 3
    assert MAX_INTERVIEW_PERSONAS == 30


def test_catalog_cost_estimates_use_each_models_real_token_prices():
    catalog = list_interview_model_catalog()

    for model in catalog["models"]:
        expected = (
            Decimal(str(model["prompt_price_per_million"]))
            * ESTIMATED_PROMPT_TOKENS_PER_MODEL_PERSONA
            + Decimal(str(model["completion_price_per_million"]))
            * ESTIMATED_COMPLETION_TOKENS_PER_MODEL_PERSONA
        ) / Decimal("1000000")
        assert Decimal(str(model["estimated_cost_per_persona_usd"])) == expected

    default_model = next(
        model for model in catalog["models"] if model["id"] == DEFAULT_INTERVIEW_MODEL_ID
    )
    default_three_person_run = (
        Decimal(str(default_model["estimated_cost_per_persona_usd"]))
        * DEFAULT_INTERVIEW_PERSONAS
        * 2
    )
    ceiling_thirty_person_run = (
        Decimal(str(default_model["estimated_cost_per_persona_usd"]))
        * MAX_INTERVIEW_PERSONAS
        * 2
    )
    assert default_three_person_run == Decimal("0.0108")
    assert ceiling_thirty_person_run == Decimal("0.108")


def test_interview_model_catalog_endpoint_serves_static_catalog(client):
    response = client.get("/api/v1/interview/models")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload == list_interview_model_catalog()
