from __future__ import annotations

import threading
import time

from src.adapters.legacy_backend import domain, jev_engine
from src.adapters.legacy_backend.runtime import load_module
from tests.test_studies_endpoints import _create_ready_to_run_study

KEY = "test-key"


def _jev_settings(app, **extra):
    """Switch the running app's settings: routes read request.app.state.settings (src/api/dependencies.py)."""
    app.state.settings = app.state.settings.model_copy(update={"typesafe_api_key": KEY, **extra})


def _jev_experiment(client, study_id, **overrides):
    payload = {"sample_size": 3, "selected_models": ["typesafe/jev"], "experiment_mode": "split", "reruns_per_persona": 1}
    payload.update(overrides)
    response = client.patch(f"/api/v1/studies/{study_id}/experiment", json=payload)
    assert response.status_code == 200
    return response


def _answer_everything(payload):
    return {"answers": {qid: ({"type": "score", "probabilities": {"0": 0, "1": 0, "2": 1, "3": 0, "4": 0}} if q["type"] == "score"
                              else {"type": "choice", "probabilities": {next(iter(q["criteria"])): 1.0}})
                        for qid, q in payload["questions"].items()}}


def test_live_jev_run_uses_the_engine_and_draws(client, app, monkeypatch):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    client.patch(f"/api/v1/studies/{study_id}/experiment", json={"sample_size": 3, "selected_models": ["typesafe/jev"],
                                                                 "experiment_mode": "split", "reruns_per_persona": 1})
    sent = []

    def fake_transport(api_key, url, **kw):
        assert api_key == "test-key"
        def send(payload):
            sent.append(payload)
            return {"answers": {qid: ({"type": "score", "probabilities": {"0": 0, "1": 0, "2": 1, "3": 0, "4": 0}} if q["type"] == "score"
                                      else {"type": "choice", "probabilities": {next(iter(q["criteria"])): 1.0}})
                                for qid, q in payload["questions"].items()}}
        return send

    monkeypatch.setattr(jev_engine, "http_transport", fake_transport)
    result = client.post(f"/api/v1/studies/{study_id}/simulation-runs").json()["data"]["simulation_run"]["result"]
    assert result["generation_mode"] == "jev_live" and result["models_used"] == ["typesafe/jev"]
    assert len(sent) == 3 and result["answer_probabilities"]
    assert all(r["answer"] == 3 for r in result["response_records"] if r["question_type"] == "likert" and not r["is_fallback"])
    assert "test-key" not in str(result)


def test_jev_with_another_model_is_rejected(client, app):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    client.patch(f"/api/v1/studies/{study_id}/experiment", json={"sample_size": 3, "selected_models": ["typesafe/jev", "openai/gpt-4o-mini"],
                                                                 "experiment_mode": "split", "reruns_per_persona": 1})
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 400 and "Jev runs on its own" in response.text


def test_catalog_lists_jev_first_when_configured(client, app):
    _jev_settings(app)
    models = client.get("/api/v1/models").json()["data"]["models"]
    assert models[0]["id"] == "typesafe/jev" and "fast, approximate" in models[0]["name"]


def test_catalog_has_no_jev_entry_without_the_key(client):
    models = client.get("/api/v1/models").json()["data"]["models"]
    assert all(model["id"] != "typesafe/jev" for model in models)


def test_catalog_keeps_the_other_models_behind_jev(client, app):
    _jev_settings(app)
    models = client.get("/api/v1/models").json()["data"]["models"]
    assert [m["id"] for m in models[1:]] == ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"]


def test_catalog_puts_jev_first_when_openrouter_lists_models(client, app, monkeypatch):
    _jev_settings(app)
    llm_client = load_module("backend.simulation.llm_client", app.state.settings.legacy_app_root)
    openrouter_models = [{"id": "mistral/small", "name": "mistral/small", "prompt_price_per_million": 1, "completion_price_per_million": 2}]
    monkeypatch.setattr(llm_client, "list_openrouter_models", lambda timeout=20: {"ok": True, "models": openrouter_models})
    payload = client.get("/api/v1/models").json()["data"]
    assert payload["source"] == "openrouter"
    assert [m["id"] for m in payload["models"]] == ["typesafe/jev", "mistral/small"]


def test_catalog_puts_jev_first_when_openrouter_errors(client, app, monkeypatch):
    _jev_settings(app)
    llm_client = load_module("backend.simulation.llm_client", app.state.settings.legacy_app_root)

    def explode(timeout=20):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm_client, "list_openrouter_models", explode)
    payload = client.get("/api/v1/models").json()["data"]
    assert payload["source"] == "fallback" and payload["models"][0]["id"] == "typesafe/jev"


def test_jev_run_in_stability_mode_is_rejected(client, app):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    _jev_experiment(client, study_id, experiment_mode="stability", reruns_per_persona=2)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 400 and "split or mirror" in response.text


def test_jev_selected_without_the_typesafe_key_is_a_503_not_an_openrouter_call(client, app, monkeypatch):
    # An OpenRouter key is set (so the run goes live), but Jev needs its own key.
    app.state.settings = app.state.settings.model_copy(update={"openrouter_api_key": "or-test-key"})
    study_id = _create_ready_to_run_study(client)
    _jev_experiment(client, study_id)
    monkeypatch.setattr(jev_engine, "http_transport", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Jev must not be called")))
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 503 and "TYPESAFE_API_KEY is required" in response.text
    assert "or-test-key" not in response.text


def test_jev_run_reports_failed_respondents_without_invented_answers_or_openrouter_wording(client, app, monkeypatch):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    _jev_experiment(client, study_id, sample_size=5)
    calls = []
    lock = threading.Lock()

    def fake_transport(api_key, url, **kw):
        def send(payload):
            with lock:
                calls.append(payload)
                first = len(calls) == 1
            if first:
                raise RuntimeError("Jev request failed after 4 attempts: HTTP 500")
            return _answer_everything(payload)
        return send

    monkeypatch.setattr(jev_engine, "http_transport", fake_transport)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 200
    run = response.json()["data"]["simulation_run"]["result"]

    assert run["generation_mode"] == "jev_live"
    assert "4 of 5 live respondents completed; 1 failed." in run["warnings"]
    assert not any("OpenRouter" in warning or "fallback" in warning.lower() for warning in run["warnings"])
    assert "OpenRouter" not in run["notes"] and "Jev" in run["notes"]
    assert run["provider_model_name"] == "typesafe/jev"
    assert run["run_counts"]["executions"] == 4
    assert len({r["respondent_id"] for r in run["response_records"]}) == 4
    assert not any(r["is_fallback"] for r in run["response_records"])
    assert run["run_debug_summary"]["primary_live_path"] is True
    assert KEY not in response.text


def test_jev_run_lists_the_questions_it_cannot_ask_and_leaves_them_unanswered(test_settings, monkeypatch):
    settings = test_settings.model_copy(update={"typesafe_api_key": KEY})
    survey = {"survey_title": "Mixed survey", "questions": [
        {"id": "Q1", "text": "How likely are you to buy?", "question_type": "likert",
         "options": ["1", "2", "3", "4", "5"], "min_value": 1, "max_value": 5, "required": True},
        {"id": "SQ1", "text": "Anything else you want to tell us?", "question_type": "open_text", "options": [], "required": True},
        {"id": "SQ2", "text": "How many rooms does your home have?", "question_type": "numeric", "options": [], "required": True},
    ]}
    monkeypatch.setattr(jev_engine, "http_transport", lambda api_key, url, **kw: _answer_everything)
    run = domain.execute_simulation_run(
        settings=settings, audience_payload={"state": "California", "age_min": 30, "age_max": 60, "homeowner_only": True},
        survey_payload=survey, experiment_payload={"sample_size": 3, "selected_models": ["typesafe/jev"], "experiment_mode": "split",
                                                   "reruns_per_persona": 1},
        product_payload=None, market_payload=None, geography_context=None)
    assert run["generation_mode"] == "jev_live"
    assert {record["question_id"] for record in run["response_records"]} == {"Q1"}
    assert len(run["response_records"]) == 3
    assert any("SQ1" in warning and "SQ2" in warning for warning in run["warnings"])
    assert KEY not in str(run)


def test_jev_down_for_every_respondent_falls_back_to_the_demo_and_the_key_stays_out_of_the_warning(client, app, monkeypatch):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    _jev_experiment(client, study_id)

    def fake_transport(api_key, url, **kw):
        def send(payload):
            raise RuntimeError("Jev request failed after 4 attempts: HTTP 500")
        return send

    monkeypatch.setattr(jev_engine, "http_transport", fake_transport)
    # No student questions in this survey, so start_simulation_run serves the preloaded demo instead of failing the run.
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 200
    run = response.json()["data"]["simulation_run"]["result"]
    assert run["generation_mode"] == "demo_preloaded"
    assert KEY not in response.text


def test_jev_run_with_too_many_failures_fails_the_run(client, app, monkeypatch):
    _jev_settings(app)
    study_id = _create_ready_to_run_study(client)
    _jev_experiment(client, study_id, sample_size=5)
    calls = []
    lock = threading.Lock()

    def fake_transport(api_key, url, **kw):
        def send(payload):
            with lock:
                calls.append(payload)
                index = len(calls)
            if index <= 2:
                raise RuntimeError("Jev request failed after 4 attempts: HTTP 500")
            return _answer_everything(payload)
        return send

    monkeypatch.setattr(jev_engine, "http_transport", fake_transport)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 503
    assert "Nothing was filled in" in response.text and KEY not in response.text


def test_neo_bootstrap_defaults_to_jev_when_the_key_is_set(client, app):
    _jev_settings(app)
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/neo")
    assert response.status_code == 200
    experiment = response.json()["data"]["study"]["experiment"]
    assert experiment["status"] == "saved"
    assert experiment["value"]["selected_models"] == ["typesafe/jev"]
    assert experiment["value"]["experiment_mode"] == "split"
    assert experiment["value"]["sample_size"] == 20


def test_neo_bootstrap_keeps_the_openrouter_models_without_the_key(client):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/neo")
    assert response.status_code == 200
    experiment = response.json()["data"]["study"]["experiment"]["value"]
    assert experiment["selected_models"] == ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"]


def test_coffee_bootstrap_stays_on_openrouter_models_even_with_the_key(client, app):
    _jev_settings(app)
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/coffee")
    assert response.status_code == 200
    experiment = response.json()["data"]["study"]["experiment"]["value"]
    assert experiment["selected_models"] == ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"]


def test_a_lone_jev_model_can_be_saved_in_split_and_mirror_modes(client):
    study_id = _create_ready_to_run_study(client)
    for mode in ("split", "mirror"):
        experiment = _jev_experiment(client, study_id, experiment_mode=mode).json()["data"]["experiment"]["value"]
        assert experiment["selected_models"] == ["typesafe/jev"] and experiment["experiment_mode"] == mode
    # Other single-model split/mirror plans stay invalid.
    response = client.patch(f"/api/v1/studies/{study_id}/experiment", json={
        "sample_size": 3, "selected_models": ["openai/gpt-4o-mini"], "experiment_mode": "split", "reruns_per_persona": 1})
    assert response.status_code == 400 and "requires at least 2 selected models" in response.text


def test_stability_check_is_refused_for_a_jev_experiment(client, app):
    _jev_settings(app, openrouter_api_key="or-test-key")
    study_id = _create_ready_to_run_study(client)
    _jev_experiment(client, study_id)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs/stability", json={"repeat_runs": 2})
    assert response.status_code == 400 and "not available for Jev runs" in response.text
    assert "or-test-key" not in response.text


def test_a_live_jev_run_uses_a_30_second_call_timeout_and_one_run_deadline(test_settings, monkeypatch):
    settings = test_settings.model_copy(update={"typesafe_api_key": KEY})
    survey = {"survey_title": "One question", "questions": [
        {"id": "Q1", "text": "How likely are you to buy?", "question_type": "likert",
         "options": ["1", "2", "3", "4", "5"], "min_value": 1, "max_value": 5, "required": True}]}
    transport_kwargs, engine_kwargs = {}, {}
    real_generate = jev_engine.generate_jev_records

    def fake_transport(api_key, url, **kw):
        transport_kwargs.update(kw)
        return _answer_everything

    def spy_generate(**kwargs):
        engine_kwargs.update(kwargs)
        return real_generate(**kwargs)

    monkeypatch.setattr(jev_engine, "http_transport", fake_transport)
    monkeypatch.setattr(jev_engine, "generate_jev_records", spy_generate)
    before = time.monotonic()
    domain.execute_simulation_run(
        settings=settings, audience_payload={"state": "California", "age_min": 30, "age_max": 60, "homeowner_only": True},
        survey_payload=survey, experiment_payload={"sample_size": 3, "selected_models": ["typesafe/jev"], "experiment_mode": "split",
                                                   "reruns_per_persona": 1},
        product_payload=None, market_payload=None, geography_context=None)
    assert transport_kwargs["timeout"] == 30
    # The transport and the engine share one monotonic deadline, 150 s after the run started.
    assert transport_kwargs["deadline"] == engine_kwargs["deadline"]
    assert before + jev_engine.JEV_RUN_DEADLINE_SECONDS <= engine_kwargs["deadline"] <= time.monotonic() + jev_engine.JEV_RUN_DEADLINE_SECONDS


def test_a_blank_student_question_is_reported_in_the_run_warnings(test_settings, monkeypatch):
    settings = test_settings.model_copy(update={"typesafe_api_key": KEY})
    survey = {"survey_title": "With a student question", "questions": [
        {"id": "Q1", "text": "How likely are you to buy?", "question_type": "likert",
         "options": ["1", "2", "3", "4", "5"], "min_value": 1, "max_value": 5, "required": True},
        {"id": "SQ1", "text": "Would solar panels make it more appealing?", "question_type": "likert",
         "options": ["1", "2", "3", "4", "5"], "min_value": 1, "max_value": 5, "required": True}]}

    def blank_sq1(payload):
        reply = _answer_everything(payload)
        reply["answers"]["SQ1"] = {"type": "score", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}}
        return reply

    monkeypatch.setattr(jev_engine, "http_transport", lambda api_key, url, **kw: blank_sq1)
    run = domain.execute_simulation_run(
        settings=settings, audience_payload={"state": "California", "age_min": 30, "age_max": 60, "homeowner_only": True},
        survey_payload=survey, experiment_payload={"sample_size": 3, "selected_models": ["typesafe/jev"], "experiment_mode": "split",
                                                   "reruns_per_persona": 1},
        product_payload=None, market_payload=None, geography_context=None)
    assert {record["question_id"] for record in run["response_records"]} == {"Q1"}
    assert "Jev gave no usable answer for some questions, so they are left blank: SQ1 (3 of 3 respondents)." in run["warnings"]
