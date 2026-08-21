"""The post-run Stability Check actually repeats the study, and had no test at all.

This is a different feature from Stability *mode*. Stability mode reruns one model against the same
personas inside a single run. The Stability Check on the Result page reruns the whole configured study
2-5 times, regenerating personas each pass, and compares the passes for repeatability.

Its only coverage was `test_start_stability_check_endpoint_returns_saved_job`, which stubs
`execute_stability_check` outright -- so the loop that does the work, the persona regeneration and the
per-repeat error handling were entirely unexercised.

Tested here at the adapter boundary, with the provider stubbed. That is the closest level at which the
repeat loop is real code rather than a mock.
"""

from __future__ import annotations

import pytest

from src.adapters.legacy_backend.domain import execute_stability_check
from src.adapters.legacy_backend.runtime import load_module
from src.services.exceptions import LegacyModuleApiError, ValidationApiError

from tests.test_legacy_live_simulation import (
    _FakeOpenRouterResponse,
    _base_run_payloads,
    _settings_with_openrouter,
)

ANSWERS = (
    '{"answers":[{"question_id":"Q1","answer":"Yes"},'
    '{"question_id":"Q2","answer":"It seems useful overall."}]}'
)


def _run(test_settings, monkeypatch, *, repeats: int, sample_size: int = 2):
    """Drive the real loop with a counting persona generator and a stubbed provider."""
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=sample_size, experiment_mode="split")
    payloads["experiment_payload"]["selected_models"] = [
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash",
    ]

    schemas = load_module("backend.schemas", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    calls = {"personas": 0, "provider": 0}

    def _generate(**kwargs):
        calls["personas"] += 1
        # A fresh draw each pass: repeatability is only meaningful if the personas are redrawn, and
        # returning the same objects would make the comparison trivially stable.
        return (
            [
                schemas.PersonaProfile(
                    persona_id=f"PERS_{calls['personas']}_{index}",
                    segment_label=f"Segment {index}",
                    fit_tier="strong",
                )
                for index in range(1, kwargs["sample_size"] + 1)
            ],
            "grounded_priors",
        )

    monkeypatch.setattr(persona_generator, "grounded_priors_available", lambda: True)
    monkeypatch.setattr(persona_generator, "generate_persona_profiles_with_mode", _generate)
    monkeypatch.setattr(persona_generator, "get_last_persona_prior_notes", lambda: [])

    def _post(url, headers, json, timeout):
        calls["provider"] += 1
        return _FakeOpenRouterResponse(ANSWERS)

    monkeypatch.setattr(llm_client.requests, "post", _post)

    result = execute_stability_check(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
        repeat_runs=repeats,
    )
    return result, calls


@pytest.mark.parametrize("repeats", [2, 3, 5])
def test_the_configured_number_of_repeats_actually_execute(test_settings, monkeypatch, repeats):
    result, calls = _run(test_settings, monkeypatch, repeats=repeats)

    assert calls["personas"] == repeats, (
        f"asked for {repeats} repeats, personas were generated {calls['personas']} time(s)"
    )
    assert len(result["run_summaries"]) == repeats, (
        f"asked for {repeats} repeats, collected {len(result['run_summaries'])} summaries"
    )


def test_personas_are_redrawn_for_each_repeat(test_settings, monkeypatch):
    """Reusing one persona set would make the check report stability it never measured."""
    _result, calls = _run(test_settings, monkeypatch, repeats=3)

    assert calls["personas"] == 3, "personas must be regenerated per pass, not reused"


def test_every_repeat_reaches_the_provider(test_settings, monkeypatch):
    """N personas x R repeats of the configured study."""
    _result, calls = _run(test_settings, monkeypatch, repeats=3, sample_size=2)

    assert calls["provider"] == 6, (
        f"expected 2 personas x 3 repeats = 6 provider calls, saw {calls['provider']}"
    )


def test_results_from_every_repeat_are_collected(test_settings, monkeypatch):
    result, _calls = _run(test_settings, monkeypatch, repeats=3)

    assert result["run_summaries"], "no summaries were returned"
    assert all(summary for summary in result["run_summaries"]), result["run_summaries"]


def test_the_repeatability_claim_is_explicitly_not_statistical(test_settings, monkeypatch):
    """The labels are heuristics. Saying so is the only thing keeping the feature honest."""
    result, _calls = _run(test_settings, monkeypatch, repeats=2)
    warnings = " ".join(result.get("warnings") or []).lower()

    assert "not formal statistical inference" in warnings, result.get("warnings")


@pytest.mark.parametrize("repeats", [1, 6])
def test_repeat_counts_outside_the_supported_range_are_refused(test_settings, monkeypatch, repeats):
    with pytest.raises(ValidationApiError):
        _run(test_settings, monkeypatch, repeats=repeats)


def test_a_failing_repeat_stops_the_check_rather_than_reporting_a_short_one(test_settings, monkeypatch):
    """Current contract: persona generation failure raises.

    Documented rather than asserted as ideal. A check that quietly returned two passes when three were
    asked for would report repeatability across a sample the user never configured.
    """
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=2, experiment_mode="split")
    payloads["experiment_payload"]["selected_models"] = [
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash",
    ]
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    state = {"n": 0}

    def _generate(**kwargs):
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("prior tables unavailable on the second pass")
        schemas = load_module("backend.schemas", settings.legacy_app_root)
        return ([schemas.PersonaProfile(persona_id="P1", segment_label="S", fit_tier="strong")], "grounded_priors")

    monkeypatch.setattr(persona_generator, "grounded_priors_available", lambda: True)
    monkeypatch.setattr(persona_generator, "generate_persona_profiles_with_mode", _generate)
    monkeypatch.setattr(persona_generator, "get_last_persona_prior_notes", lambda: [])
    monkeypatch.setattr(
        llm_client.requests, "post", lambda url, headers, json, timeout: _FakeOpenRouterResponse(ANSWERS)
    )

    with pytest.raises(LegacyModuleApiError) as excinfo:
        execute_stability_check(
            settings=settings,
            audience_payload=payloads["audience_payload"],
            survey_payload=payloads["survey_payload"],
            experiment_payload=payloads["experiment_payload"],
            product_payload=payloads["product_payload"],
            market_payload=payloads["market_payload"],
            geography_context=None,
            repeat_runs=3,
        )

    assert "persona generation failed" in str(excinfo.value).lower()
