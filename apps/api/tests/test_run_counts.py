"""F-05: a run reports three different quantities, all of them called "responses".

A mirror run of N personas across M models performs N x M provider round-trips and stores
N x M x questions answer rows. Three numbers were derived from that and none of them said which:

- `total_generated_responses` was always `sample_size`, because the legacy entry point sets
  `total_generated = config.sample_size` and the adapter's kwarg shim silently drops what it is given.
- The Result tile counted distinct `respondent_id`, which mirror mode deliberately reuses across models,
  so mirror was under-reported by a factor of M.
- Only the Analysis view exposed the record count.

A 20-persona x 2-model x 32-question mirror run performs 40 executions and stores 1,280 rows while the
summary reads "20". The quantities are all real; the reporting has to name which one it means.
"""

from __future__ import annotations

import json

import pytest

from src.adapters.legacy_backend.domain import execute_simulation_run
from src.adapters.legacy_backend.runtime import load_module

from tests.test_legacy_live_simulation import (
    _FakeOpenRouterResponse,
    _base_run_payloads,
    _patch_grounded_personas,
    _settings_with_openrouter,
)


def _patch_n_personas(monkeypatch, settings, sample_size: int):
    """The shared helper only ever yields two personas, which caps `personas` below N above N=2."""
    schemas = load_module("backend.schemas", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    prior_sampler = load_module("backend.grounding.prior_sampler", settings.legacy_app_root)

    personas = [
        schemas.PersonaProfile(
            persona_id=f"PERS_{index:03d}", segment_label=f"Segment {index}", fit_tier="strong"
        )
        for index in range(1, sample_size + 1)
    ]
    monkeypatch.setattr(persona_generator, "grounded_priors_available", lambda: True)
    monkeypatch.setattr(prior_sampler, "cex_affordability_priors_available", lambda: True)
    monkeypatch.setattr(
        persona_generator,
        "generate_persona_profiles_with_mode",
        lambda **kwargs: (personas[: kwargs["sample_size"]], "grounded_priors"),
    )
    monkeypatch.setattr(persona_generator, "get_last_persona_prior_notes", lambda: [])


def _mirror_run(test_settings, monkeypatch, *, sample_size: int = 2):
    """Two personas x two models over the two-question fixture survey."""
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=sample_size, experiment_mode="mirror")
    payloads["experiment_payload"]["selected_models"] = [
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash",
    ]
    _patch_grounded_personas(monkeypatch, settings, sample_size=sample_size)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    monkeypatch.setattr(
        llm_client.requests,
        "post",
        lambda url, headers, json, timeout: _FakeOpenRouterResponse(
            '{"answers":[{"question_id":"Q1","answer":"Yes"},'
            '{"question_id":"Q2","answer":"It seems useful overall."}]}'
        ),
    )

    return execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )


def test_run_reports_personas_executions_and_answer_records_separately(test_settings, monkeypatch):
    """Each quantity is named, so no reader has to guess which one a number refers to."""
    result = _mirror_run(test_settings, monkeypatch)
    counts = result["run_counts"]

    assert counts["personas"] == 2, "two simulated people"
    assert counts["executions"] == 4, "each persona answered the survey once per model"
    assert counts["questions"] == 2
    assert counts["answer_records"] == 8, "one row per execution per question"


def test_generated_responses_counts_executions_not_personas(test_settings, monkeypatch):
    """The headline count must not ignore the models it ran against.

    This is the value that previously read `sample_size` regardless of mode, models, reruns, or whether
    any provider call succeeded.
    """
    result = _mirror_run(test_settings, monkeypatch)

    assert result["total_generated_responses"] == 4, (
        "a 2-persona x 2-model mirror run produces four completed responses, not two"
    )
    assert result["total_requested_responses"] == 4


def test_counts_reconcile_with_the_saved_records(test_settings, monkeypatch):
    """The reported numbers have to match what is actually stored, or they are just another claim."""
    result = _mirror_run(test_settings, monkeypatch)
    counts = result["run_counts"]
    records = result["response_records"]

    assert counts["answer_records"] == len(records)
    assert counts["personas"] == len({record["respondent_id"] for record in records})
    assert counts["executions"] == len(
        {(record["respondent_id"], record["model"]) for record in records}
    ), "mirror reuses respondent ids across models, so executions are respondent-model pairs"
    assert counts["executions"] * counts["questions"] == counts["answer_records"]


def test_split_mode_counts_one_execution_per_persona(test_settings, monkeypatch):
    """Split allocates each persona to a single model, so executions equal personas."""
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=2)
    payloads["experiment_payload"]["selected_models"] = [
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash",
    ]
    _patch_grounded_personas(monkeypatch, settings, sample_size=2)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    monkeypatch.setattr(
        llm_client.requests,
        "post",
        lambda url, headers, json, timeout: _FakeOpenRouterResponse(
            '{"answers":[{"question_id":"Q1","answer":"Yes"},'
            '{"question_id":"Q2","answer":"It seems useful overall."}]}'
        ),
    )

    result = execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )
    counts = result["run_counts"]

    assert counts["personas"] == 2
    assert counts["executions"] == 2
    assert counts["answer_records"] == 4
    assert result["total_generated_responses"] == 2


def test_counts_are_serializable_for_the_job_envelope(test_settings, monkeypatch):
    """The whole result is persisted as JSON in jobs.result_json."""
    result = _mirror_run(test_settings, monkeypatch)
    assert json.loads(json.dumps(result["run_counts"])) == result["run_counts"]


@pytest.mark.parametrize(
    "mode,sample_size,models,reruns,expected_executions",
    [
        ("split", 3, 2, 1, 3),        # each persona answers once, allocated round-robin
        ("split", 4, 2, 1, 4),
        ("mirror", 3, 2, 1, 6),       # every persona answers once per model
        ("mirror", 2, 2, 1, 4),
        ("stability", 3, 2, 2, 6),    # every persona repeats, against the first model only
        ("stability", 2, 2, 3, 6),
    ],
)
def test_execution_and_record_counts_for_every_mode(
    test_settings, monkeypatch, mode, sample_size, models, reruns, expected_executions
):
    """The three modes allocate work differently, and each has its own arithmetic.

    split      executions = N            records = N x Q
    mirror     executions = N x M        records = N x M x Q
    stability  executions = N x R        records = N x R x Q   (first selected model only)
    """
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=sample_size, experiment_mode=mode)
    payloads["experiment_payload"]["selected_models"] = [
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash",
    ][:models]
    payloads["experiment_payload"]["reruns_per_persona"] = reruns
    _patch_n_personas(monkeypatch, settings, sample_size)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    monkeypatch.setattr(
        llm_client.requests,
        "post",
        lambda url, headers, json, timeout: _FakeOpenRouterResponse(
            '{"answers":[{"question_id":"Q1","answer":"Yes"},'
            '{"question_id":"Q2","answer":"It seems useful overall."}]}'
        ),
    )

    result = execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )
    counts = result["run_counts"]
    questions = counts["questions"]

    assert counts["personas"] == sample_size
    assert counts["executions"] == expected_executions, (
        f"{mode} with N={sample_size} M={models} R={reruns}"
    )
    assert counts["answer_records"] == expected_executions * questions
    assert counts["answer_records"] == len(result["response_records"])


def test_mirror_aligns_respondent_ids_across_models(test_settings, monkeypatch):
    """Mirror exists so the same simulated person can be compared across models.

    If the ids diverged, every per-model comparison would be comparing different people while
    reporting that it was not.
    """
    result = _mirror_run(test_settings, monkeypatch, sample_size=3)
    records = result["response_records"]

    by_model: dict = {}
    for record in records:
        by_model.setdefault(record["model"], set()).add(record["respondent_id"])

    assert len(by_model) == 2
    first, second = by_model.values()
    assert first == second, f"mirror respondent ids diverged across models: {by_model}"


def test_stability_encodes_reruns_and_uses_only_the_first_model(test_settings, monkeypatch):
    """Stability repeats one model against the same personas, so reruns must be distinguishable."""
    settings = _settings_with_openrouter(test_settings)
    payloads = _base_run_payloads(sample_size=2, experiment_mode="stability")
    payloads["experiment_payload"]["selected_models"] = [
        "openai/gpt-4o-mini",
        "google/gemini-2.5-flash",
    ]
    payloads["experiment_payload"]["reruns_per_persona"] = 3
    _patch_n_personas(monkeypatch, settings, 2)

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    monkeypatch.setattr(
        llm_client.requests,
        "post",
        lambda url, headers, json, timeout: _FakeOpenRouterResponse(
            '{"answers":[{"question_id":"Q1","answer":"Yes"},'
            '{"question_id":"Q2","answer":"It seems useful overall."}]}'
        ),
    )
    result = execute_simulation_run(
        settings=settings,
        audience_payload=payloads["audience_payload"],
        survey_payload=payloads["survey_payload"],
        experiment_payload=payloads["experiment_payload"],
        product_payload=payloads["product_payload"],
        market_payload=payloads["market_payload"],
        geography_context=None,
    )
    records = result["response_records"]

    assert {record["model"] for record in records} == {"openai/gpt-4o-mini"}, (
        "stability compares a model against itself, so only the first selected model runs"
    )

    respondent_ids = sorted({record["respondent_id"] for record in records})
    assert len(respondent_ids) == 6, respondent_ids
    assert all("_R" in respondent_id for respondent_id in respondent_ids), (
        f"reruns are not distinguishable in the saved ids: {respondent_ids}"
    )
    assert {rid.split("_R")[0] for rid in respondent_ids} == {"RESP_001", "RESP_002"}
