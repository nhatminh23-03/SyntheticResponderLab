from __future__ import annotations

import pytest

from tests.test_studies_endpoints import _create_ready_to_run_study


def _fail_if_called(*args, **kwargs):
    raise AssertionError("a provider was called")


def _jev_down(**kwargs):
    from src.adapters.legacy_backend.jev_engine import JevUnavailableError
    raise JevUnavailableError("Jev did not answer any respondent: timeout")


def _add_student_question(client, study_id: str) -> None:
    # Task 7's endpoint does not exist yet; append a student question through the existing "accept survey" endpoint.
    study = client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]
    survey = dict(study["survey"]["schema"])
    survey["questions"] = survey["questions"] + [{"id": "SQ1", "text": "Would solar panels make this product more appealing?",
                                                  "question_type": "likert", "options": ["1", "2", "3", "4", "5"],
                                                  "min_value": 1, "max_value": 5, "required": True}]
    assert client.post(f"/api/v1/studies/{study_id}/survey/generated", json={"survey_schema": survey}).status_code == 200


def test_demo_source_never_calls_a_provider_and_renders_analysis(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"})
    assert response.status_code == 200
    result = response.json()["data"]["simulation_run"]["result"]
    assert result["generation_mode"] == "demo_preloaded" and result["demo"]["reason"] == "requested"
    assert not any("Run live to answer" in w for w in result["warnings"])   # the Neo preset is fully covered
    analysis = client.get(f"/api/v1/studies/{study_id}/analysis")
    assert analysis.status_code == 200
    # The web decides "preloaded demo" from this field, not from the shape of the run id.
    assert analysis.json()["data"]["analysis"]["run"]["generation_mode"] == "demo_preloaded"
    assert client.get(f"/api/v1/studies/{study_id}/insights").status_code == 200


def test_live_without_any_key_falls_back_to_demo(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    result = client.post(f"/api/v1/studies/{study_id}/simulation-runs").json()["data"]["simulation_run"]["result"]
    assert result["demo"]["reason"] == "no_key"


def test_jev_down_on_the_original_survey_falls_back_to_demo_visibly(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service._live_engine_configured", lambda settings: True)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _jev_down)
    result = client.post(f"/api/v1/studies/{study_id}/simulation-runs").json()["data"]["simulation_run"]["result"]
    assert result["demo"]["reason"] == "jev_unavailable"
    assert any("Jev is temporarily unavailable" in w for w in result["warnings"])


def test_jev_down_with_a_student_question_is_not_replaced_by_demo_answers(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    _add_student_question(client, study_id)
    monkeypatch.setattr("src.services.study_service._live_engine_configured", lambda settings: True)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _jev_down)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 503
    assert "Your new question requires a live run" in response.text
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest is None or latest["status"] == "failed"   # no demo answers were saved for this run


def test_unknown_source_is_rejected(client):
    study_id = _create_ready_to_run_study(client)
    assert client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "fake"}).status_code in (400, 422)


def test_live_with_no_key_and_a_student_question_is_not_replaced_by_demo_answers(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    _add_student_question(client, study_id)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "live"})
    assert response.status_code == 503
    assert "Your new question requires a live run" in response.text
    assert response.json()["error"]["details"] == {"retry": False, "demo_available": True}
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest is None or latest["status"] != "completed"   # no demo run was saved for this request


def test_explicit_demo_with_a_student_question_serves_the_demo_with_the_run_live_note(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    _add_student_question(client, study_id)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"})
    assert response.status_code == 200
    result = response.json()["data"]["simulation_run"]["result"]
    assert result["generation_mode"] == "demo_preloaded" and result["demo"]["reason"] == "requested"
    assert any("Run live to answer these: SQ1" in w for w in result["warnings"])


def test_insights_on_a_demo_run_never_call_a_provider_even_when_a_key_is_configured(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    keyed = client.app.state.settings.model_copy(update={"openrouter_api_key": "test-openrouter-key"})
    monkeypatch.setattr(client.app.state, "settings", keyed)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    monkeypatch.setattr("src.services.study_service._generate_llm_insights_summary", _fail_if_called)
    monkeypatch.setattr("src.services.study_service._request_llm_insights_summary", _fail_if_called)
    run = client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"})
    assert run.status_code == 200
    assert run.json()["data"]["simulation_run"]["result"]["generation_mode"] == "demo_preloaded"
    response = client.get(f"/api/v1/studies/{study_id}/insights")
    assert response.status_code == 200
    insights = response.json()["data"]["insights"]
    assert insights["available"] is True   # the rule-based detailed insights still render
    assert insights["llm_summary"]["available"] is False
    assert "No AI was called" in insights["llm_summary"]["message"]
    assert insights["llm_summary"]["cached"] is False
    assert insights["llm_summary"]["model"] is None   # no model chip on demo data: no model wrote this
    assert insights["run"]["generation_mode"] == "demo_preloaded"   # the web words the Insights header from this


@pytest.mark.parametrize("error_name, message", [
    ("JevRequestError", "Jev refused the request: invalid key"),
    ("JevTooManyFailuresError", "Jev failed for 31 of 100 respondents (more than 20%). Retry the run."),
])
def test_jev_refusal_and_too_many_failures_stay_503_and_never_become_demo_answers(
    client, monkeypatch, live_engine_configured, error_name, message
):
    import src.adapters.legacy_backend.jev_engine as jev_engine

    error_class = getattr(jev_engine, error_name)

    def _raise(**kwargs):
        raise error_class(message)

    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _raise)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 503
    assert response.json()["error"]["message"] == message
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest["status"] == "failed" and latest["result"] is None   # no demo answers were saved for this run
    assert latest["error"]["message"] == message


def _checked_out_connections(client) -> int:
    return client.app.state.session_factory.kw["bind"].pool.checkedout()


def test_no_database_connection_is_held_while_the_live_provider_runs(client, monkeypatch, live_engine_configured):
    from src.services.demo_survey_run import build_demo_run_result

    study_id = _create_ready_to_run_study(client)
    seen = []

    def provider(**kwargs):
        seen.append(_checked_out_connections(client))
        return build_demo_run_result(survey_payload=kwargs["survey_payload"], experiment_payload=kwargs["experiment_payload"],
                                     reason="requested")

    monkeypatch.setattr("src.services.study_service.execute_simulation_run", provider)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 200
    assert seen == [0]
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest["status"] == "completed" and latest["result"]["run_id"].startswith("DEMO_")


def test_no_database_connection_is_held_while_the_demo_or_the_jev_down_fallback_is_built(client, monkeypatch):
    import src.services.study_service as study_service

    real_build = study_service.build_demo_run_result
    seen = []

    def spy_build(**kwargs):
        seen.append(("demo", _checked_out_connections(client)))
        return real_build(**kwargs)

    def jev_down(**kwargs):
        seen.append(("provider", _checked_out_connections(client)))
        _jev_down(**kwargs)

    monkeypatch.setattr("src.services.study_service.build_demo_run_result", spy_build)
    study_id = _create_ready_to_run_study(client)
    assert client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"}).status_code == 200
    monkeypatch.setattr("src.services.study_service._live_engine_configured", lambda settings: True)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", jev_down)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 200 and response.json()["data"]["simulation_run"]["result"]["demo"]["reason"] == "jev_unavailable"
    assert seen == [("demo", 0), ("provider", 0), ("demo", 0)]


def test_a_failed_provider_call_still_saves_the_run_as_failed_after_the_connection_was_released(client, monkeypatch, live_engine_configured):
    study_id = _create_ready_to_run_study(client)

    def provider(**kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr("src.services.study_service.execute_simulation_run", provider)
    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest["status"] == "failed" and latest["error"]["message"] == "provider exploded"


def _replace_survey_with_one_the_demo_does_not_cover(client, study_id: str) -> None:
    study = client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]
    survey = dict(study["survey"]["schema"])
    survey["questions"] = [{"id": "C1", "text": "How likely are you to buy this coffee maker?", "question_type": "likert",
                            "options": ["1", "2", "3", "4", "5"], "min_value": 1, "max_value": 5, "required": True}]
    assert client.post(f"/api/v1/studies/{study_id}/survey/generated", json={"survey_schema": survey}).status_code == 200


def test_jev_down_on_a_survey_the_demo_does_not_cover_says_jev_is_down(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    _replace_survey_with_one_the_demo_does_not_cover(client, study_id)
    monkeypatch.setattr("src.services.study_service._live_engine_configured", lambda settings: True)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _jev_down)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["message"] == ("Jev is temporarily unavailable, and the preloaded demo does not cover this survey. "
                                "Please retry in a minute.")
    assert error["details"] == {"retry": True, "demo_available": False}
    latest = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest").json()["data"]["simulation_run"]
    assert latest["status"] == "failed" and latest["result"] is None


def test_asking_for_the_demo_on_a_survey_it_does_not_cover_still_says_so(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    _replace_survey_with_one_the_demo_does_not_cover(client, study_id)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"})
    assert response.status_code == 409 and "preloaded demo covers the Tahoe Mini survey" in response.text
