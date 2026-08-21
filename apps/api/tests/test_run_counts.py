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

from src.adapters.legacy_backend.domain import execute_simulation_run
from src.adapters.legacy_backend.runtime import load_module

from tests.test_legacy_live_simulation import (
    _FakeOpenRouterResponse,
    _base_run_payloads,
    _patch_grounded_personas,
    _settings_with_openrouter,
)


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
