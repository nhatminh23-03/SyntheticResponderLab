"""AI survey generation: drafting, refinement, and acceptance.

Generation is provider-backed, so these tests stub the LLM call and focus on the
contract around it: context requirements, validation of whatever the model
returns, and the fact that a draft is not persisted until explicitly accepted.
"""

from __future__ import annotations

import json

import pytest

from src.adapters.legacy_backend import domain


def _model_response(questions: list[dict], summary: str = "A drafted survey.") -> dict:
    payload = {
        "survey_title": "Generated Survey",
        "description": "Drafted for tests.",
        "summary": summary,
        "questions": questions,
    }
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _likert(index: int) -> dict:
    return {
        "id": f"Q{index}",
        "text": f"How much do you agree with statement {index}?",
        "question_type": "likert",
        "options": [],
        "min_value": 1,
        "max_value": 5,
        "required": True,
    }


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def stub_provider(client, monkeypatch):
    """Capture the outgoing request and return a scripted model response."""
    # Generation refuses to run without a provider key; tests stub the call itself.
    client.app.state.settings.openrouter_api_key = "test-openrouter-key"
    calls: list[dict] = []

    def install(payload: dict, status_code: int = 200, text: str = ""):
        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append({"url": url, "body": json})
            return _FakeResponse(payload, status_code=status_code, text=text)

        monkeypatch.setattr(domain.requests, "post", fake_post)
        return calls

    return install


PRODUCT_PAYLOAD = {
    "business_name": "Cortado Roasters",
    "product_name": "Everyday Origins",
    "product_description": "A roast-to-order coffee subscription shipped within 24 hours.",
    "price_range": "$19 per 12 oz bag",
}


def _ready_general_study(client) -> str:
    """A general-mode study with just enough saved context to generate against."""
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.patch(f"/api/v1/studies/{study_id}/study-mode", json={"study_mode": "general"})
    client.patch(f"/api/v1/studies/{study_id}/product", json=PRODUCT_PAYLOAD)
    return study_id


def test_generation_requires_saved_product(client, stub_provider):
    stub_provider(_model_response([_likert(i) for i in range(1, 6)]))
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 5}
    )

    assert response.status_code == 400
    assert "Product" in response.json()["error"]["message"]


def test_generate_returns_validated_draft_without_saving(client, stub_provider):
    stub_provider(_model_response([_likert(i) for i in range(1, 6)]))
    study_id = _ready_general_study(client)

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 5}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["question_count"] == 5
    assert data["summary"] == "A drafted survey."
    assert len(data["survey_schema"]["questions"]) == 5

    # Generating must not touch the saved survey section.
    saved = client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]["survey"]
    assert saved["status"] != "saved"


def test_generation_sends_product_context_to_the_model(client, stub_provider):
    calls = stub_provider(_model_response([_likert(i) for i in range(1, 4)]))
    study_id = _ready_general_study(client)

    client.post(f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 3})

    assert calls, "provider was not called"
    prompt = calls[-1]["body"]["messages"][-1]["content"]
    assert "Cortado Roasters" in prompt
    assert "Everyday Origins" in prompt
    assert "Produce exactly 3 questions." in prompt


def test_refinement_forwards_previous_draft_and_instruction(client, stub_provider):
    calls = stub_provider(_model_response([_likert(i) for i in range(1, 4)]))
    study_id = _ready_general_study(client)

    first = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 3}
    ).json()["data"]

    client.post(
        f"/api/v1/studies/{study_id}/survey/generate",
        json={
            "question_count": 3,
            "instructions": "Add a price sensitivity question.",
            "previous_schema": first["survey_schema"],
            "conversation": [{"role": "assistant", "content": first["summary"]}],
        },
    )

    prompt = calls[-1]["body"]["messages"][-1]["content"]
    assert "You previously drafted this survey" in prompt
    assert "Add a price sensitivity question." in prompt
    assert "ASSISTANT SAID: A drafted survey." in prompt


def test_question_count_mismatch_is_reported_as_a_warning(client, stub_provider):
    stub_provider(_model_response([_likert(i) for i in range(1, 4)]))
    study_id = _ready_general_study(client)

    data = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 10}
    ).json()["data"]

    assert data["question_count"] == 3
    assert any("Requested 10" in warning for warning in data["warnings"])


def test_out_of_range_question_count_is_rejected(client):
    study_id = _ready_general_study(client)

    for count in (2, 61):
        response = client.post(
            f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": count}
        )
        assert response.status_code == 400, count


def test_invalid_model_output_is_surfaced_not_saved(client, stub_provider):
    stub_provider({"choices": [{"message": {"content": "I am not JSON."}}]})
    study_id = _ready_general_study(client)

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 5}
    )

    assert response.status_code == 503
    assert "JSON" in response.json()["error"]["message"]


def test_provider_error_detail_is_surfaced(client, stub_provider):
    stub_provider(
        {"error": {"message": "context length exceeded"}},
        status_code=400,
        text=json.dumps({"error": {"message": "context length exceeded"}}),
    )
    study_id = _ready_general_study(client)

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 5}
    )

    assert response.status_code == 503
    # The provider's reason must reach the user, not just the status code.
    assert "context length exceeded" in response.json()["error"]["message"]


def test_accepting_a_draft_replaces_the_saved_survey(client, stub_provider):
    stub_provider(_model_response([_likert(i) for i in range(1, 7)]))
    study_id = _ready_general_study(client)

    draft = client.post(
        f"/api/v1/studies/{study_id}/survey/generate", json={"question_count": 6}
    ).json()["data"]["survey_schema"]

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/generated", json={"survey_schema": draft}
    )

    assert response.status_code == 200
    survey = response.json()["data"]["survey"]
    assert survey["status"] == "saved"
    assert survey["question_count"] == 6
    assert survey["source_filename"] == "ai-generated-survey.json"


def test_accepting_an_invalid_draft_is_rejected(client):
    study_id = _ready_general_study(client)

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/generated",
        json={"survey_schema": {"survey_title": "Broken", "questions": []}},
    )

    assert response.status_code == 400
