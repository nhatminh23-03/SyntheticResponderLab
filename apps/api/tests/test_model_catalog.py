from __future__ import annotations

from src.services.model_catalog import (
    DEFAULT_INTERVIEW_MODEL_ID,
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
    assert [model["tier"] for model in catalog["models"]] == [
        "cheap",
        "cheap",
        "mid",
        "mid",
        "expensive",
        "expensive",
    ]


def test_interview_model_catalog_endpoint_serves_static_catalog(client):
    response = client.get("/api/v1/interview/models")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload == list_interview_model_catalog()
