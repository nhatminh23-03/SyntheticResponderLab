from __future__ import annotations

from src.adapters.legacy_backend.domain import execute_simulation_run
from src.adapters.legacy_backend.runtime import load_module
from src.services.exceptions import ProviderUnavailableApiError


class _FakeOpenRouterResponse:
    def __init__(self, content: str, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = content
        self._payload = {
            "choices": [
                {
                    "message": {
                        "content": content,
                    }
                }
            ]
        }

    def json(self):
        return self._payload


def _settings_with_openrouter(test_settings):
    return test_settings.model_copy(update={"openrouter_api_key": "test-openrouter-key"})


def _patch_grounded_personas(monkeypatch, settings, sample_size: int):
    schemas = load_module("backend.schemas", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    prior_sampler = load_module("backend.grounding.prior_sampler", settings.legacy_app_root)

    personas = [
        schemas.PersonaProfile(persona_id="PERS_001", segment_label="Remote Professionals", fit_tier="high"),
        schemas.PersonaProfile(persona_id="PERS_002", segment_label="Budget-Conscious Owners", fit_tier="medium"),
    ][:sample_size]

    monkeypatch.setattr(persona_generator, "grounded_priors_available", lambda: True)
    monkeypatch.setattr(prior_sampler, "cex_affordability_priors_available", lambda: True)
    monkeypatch.setattr(
        persona_generator,
        "generate_persona_profiles_with_mode",
        lambda **kwargs: (personas[: kwargs["sample_size"]], "grounded_priors"),
    )
    monkeypatch.setattr(
        persona_generator,
        "get_last_persona_prior_notes",
        lambda: [{"table": "age_income", "filter_level_used": "global", "narrowed": False}],
    )


def _base_run_payloads(sample_size: int = 2, experiment_mode: str = "split"):
    return {
        "audience_payload": {
            "state": "California",
            "age_min": 30,
            "age_max": 55,
            "homeowner_only": True,
        },
        "survey_payload": {
            "survey_title": "Live Survey Test",
            "questions": [
                {
                    "id": "Q1",
                    "text": "Would you consider this product?",
                    "question_type": "single_choice",
                    "options": ["Yes", "No"],
                },
                {
                    "id": "Q2",
                    "text": "Why?",
                    "question_type": "open_text",
                },
            ],
        },
        "experiment_payload": {
            "sample_size": sample_size,
            "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": experiment_mode,
            "reruns_per_persona": 1,
        },
        "product_payload": {
            "business_name": "Neo Smart Living",
            "product_name": "Tahoe Mini",
            "product_type": "Backyard studio",
        },
        "market_payload": {
            "category": "Backyard prefab studio",
            "substitutes": ["Traditional shed"],
        },
    }


def test_execute_simulation_run_requires_openrouter_key(test_settings):
    payloads = _base_run_payloads(sample_size=1)

    try:
        execute_simulation_run(
            settings=test_settings,
            audience_payload=payloads["audience_payload"],
            survey_payload=payloads["survey_payload"],
            experiment_payload=payloads["experiment_payload"],
            product_payload=payloads["product_payload"],
            market_payload=payloads["market_payload"],
            geography_context=None,
        )
    except ProviderUnavailableApiError as exc:
        assert "OPENROUTER_API_KEY is required" in exc.message
    else:
        raise AssertionError("Expected execute_simulation_run to require an OpenRouter API key.")


def test_execute_simulation_run_uses_live_selected_models(test_settings, monkeypatch):
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=2, experiment_mode="split")
    _patch_grounded_personas(monkeypatch, settings, sample_size=2)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    def fake_post(url, headers, json, timeout):
        model = json["model"]
        if model == "openai/gpt-4o-mini":
            return _FakeOpenRouterResponse(
                '{"answers":[{"question_id":"Q1","answer":"Yes"},{"question_id":"Q2","answer":"Strong home office fit."}]}'
            )
        return _FakeOpenRouterResponse(
            '{"answers":[{"question_id":"Q1","answer":"No"},{"question_id":"Q2","answer":"Budget is still the main concern."}]}'
        )

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    result = execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )

    assert result["generation_mode"] == "openrouter_live"
    assert result["provider_model_name"] is None
    assert result["total_generated_responses"] == 4
    assert set(result["models_used"]) == {"openai/gpt-4o-mini", "google/gemini-2.0-flash-001"}
    assert {record["model"] for record in result["response_records"]} == {
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
    }
    assert result["generation_debug"]["questions_fallback_to_mock"] == 0
    assert result["generation_debug"]["questions_parsed_from_live"] == 4
    assert result["generation_debug"]["provider_error_count"] == 0
    assert result["generation_debug"]["malformed_json_count"] == 0
    assert result["run_debug_summary"]["primary_live_path"] is True
    assert result["run_debug_summary"]["truly_live_answers"] == 4
    assert result["run_debug_summary"]["fallback_answers"] == 0
    assert result["run_debug_summary"]["ml_persona_completion_enabled"] is False


def test_execute_simulation_run_reports_temporary_fallback_usage(test_settings, monkeypatch):
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=1, experiment_mode="split")
    payloads["experiment_payload"]["selected_models"] = ["openai/gpt-4o-mini"]
    _patch_grounded_personas(monkeypatch, settings, sample_size=1)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    def fake_post(url, headers, json, timeout):
        return _FakeOpenRouterResponse(
            '{"answers":[{"question_id":"Q1","answer":"Maybe"},{"question_id":"Q2","answer":"I still like the concept overall."}]}'
        )

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    result = execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )

    q1_record = next(record for record in result["response_records"] if record["question_id"] == "Q1")
    q2_record = next(record for record in result["response_records"] if record["question_id"] == "Q2")

    assert q1_record["answer"] in {"Yes", "No"}
    assert q2_record["answer"] == "I still like the concept overall."
    assert result["generation_debug"]["questions_fallback_to_mock"] == 1
    assert result["generation_debug"]["questions_parsed_from_live"] == 1
    assert any("Temporary migration fallback was used" in warning for warning in result["warnings"])


def test_execute_simulation_run_counts_malformed_json_fallbacks(test_settings, monkeypatch):
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=1, experiment_mode="split")
    payloads["experiment_payload"]["selected_models"] = ["openai/gpt-4o-mini"]
    _patch_grounded_personas(monkeypatch, settings, sample_size=1)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    def fake_post(url, headers, json, timeout):
        return _FakeOpenRouterResponse("not valid json")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    result = execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )

    assert result["generation_debug"]["request_errors"] == 1
    assert result["generation_debug"]["provider_error_count"] == 0
    assert result["generation_debug"]["malformed_json_count"] == 1
    assert result["generation_debug"]["questions_fallback_to_mock"] == 2
    assert result["run_debug_summary"]["fallback_answers"] == 2
    assert any("malformed JSON" in warning for warning in result["warnings"])
