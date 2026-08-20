"""Demo presets must set up a runnable study for any product category.

The coffee preset exists to exercise the product-agnostic claim: it runs in
`general` mode with its own bundled survey, a different audience shape, and a
category unrelated to the Neo Smart preset.
"""

from __future__ import annotations

import pytest

from src.services.study_service import COFFEE_DEMO_PRESET, DEMO_PRESETS, NEO_DEMO_PRESET


def _new_study(client) -> str:
    return client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]


def test_preset_registry_covers_both_modes():
    assert set(DEMO_PRESETS) == {"neo", "coffee"}
    assert NEO_DEMO_PRESET.study_mode == "neo_smart"
    assert COFFEE_DEMO_PRESET.study_mode == "general"
    # The Neo survey loads through the legacy preset module; coffee ships its own file.
    assert NEO_DEMO_PRESET.survey_filename is None
    assert COFFEE_DEMO_PRESET.survey_filename is not None


def test_unknown_preset_returns_404(client):
    study_id = _new_study(client)
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/tacos")

    assert response.status_code == 404
    assert "Unknown demo preset" in response.json()["error"]["message"]


def test_coffee_preset_bootstraps_a_runnable_general_study(client):
    study_id = _new_study(client)
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/coffee")

    assert response.status_code == 200
    study = response.json()["data"]["study"]

    assert study["study_mode"]["value"] == "general"
    assert study["product"]["value"]["business_name"] == "Cortado Roasters"
    assert study["product"]["value"]["product_name"] == "Everyday Origins"
    assert study["market"]["value"]["category"] == "Direct-to-consumer specialty coffee subscription"

    for section in ("audience", "product", "market", "survey", "experiment"):
        assert study[section]["status"] == "saved", f"{section} was not saved"

    assert study["survey"]["question_count"] == 32
    assert study["survey"]["source_format"] == "md"


def test_coffee_preset_audience_differs_from_neo(client):
    """The two presets must not collapse onto the same audience assumptions."""
    coffee_id = _new_study(client)
    coffee = client.post(
        f"/api/v1/studies/{coffee_id}/study-mode/bootstrap/preset/coffee"
    ).json()["data"]["study"]["audience"]["value"]

    neo_id = _new_study(client)
    neo = client.post(
        f"/api/v1/studies/{neo_id}/study-mode/bootstrap/preset/neo"
    ).json()["data"]["study"]["audience"]["value"]

    # Neo targets homeowners with backyard space; coffee must include renters.
    assert neo["homeowner_only"] is True
    assert coffee["homeowner_only"] is False
    assert coffee["home_type"] is None


def test_coffee_survey_questions_are_typed_and_scaled(client):
    study_id = _new_study(client)
    study = client.post(
        f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/coffee"
    ).json()["data"]["study"]

    questions = study["survey"]["schema"]["questions"]
    assert len(questions) == 32

    by_type: dict[str, int] = {}
    for question in questions:
        by_type[question["question_type"]] = by_type.get(question["question_type"], 0) + 1
    assert by_type == {"likert": 25, "single_choice": 7}

    for question in questions:
        if question["question_type"] == "likert":
            assert question["min_value"] == 1
            assert question["max_value"] == 5
        else:
            assert question["options"], f"{question['id']} has no options"

    # The barrier matrix must expand into per-row questions.
    barrier_ids = [q["id"] for q in questions if q["id"].startswith("Q7_")]
    assert len(barrier_ids) == 6


def test_generic_endpoint_still_bootstraps_neo(client):
    study_id = _new_study(client)
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/neo")

    assert response.status_code == 200
    study = response.json()["data"]["study"]
    assert study["study_mode"]["value"] == "neo_smart"
    assert study["product"]["value"]["product_name"] == "Tahoe Mini"
