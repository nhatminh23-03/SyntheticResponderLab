from __future__ import annotations

from tests.test_studies_endpoints import _create_ready_to_run_study


def _fail_if_called(**kwargs):
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
    assert client.get(f"/api/v1/studies/{study_id}/analysis").status_code == 200
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
