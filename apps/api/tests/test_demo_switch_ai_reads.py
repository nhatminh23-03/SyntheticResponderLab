"""The web's Demo (no AI) switch is browser-only; the two insight reads that can call a model take `ai=false` from it.

With `ai=false` a read serves a summary or themes already cached for the run, and otherwise says why there is none.
It never reaches a provider. Without the parameter (or with `ai=true`) the reads behave exactly as before.
"""
from __future__ import annotations

import json

from sqlalchemy import select

from src.persistence.models import Study, StudySectionState
from src.services.interview_service import DEMO_SWITCH_NO_AI_THEMES
from src.services.study_service import DEMO_SWITCH_NO_AI_SUMMARY
from tests.test_studies_endpoints import _create_ready_to_run_study, _mock_insights_run_payload
from tests.test_usage_limits import _bootstrap_neo_study_for_interviews


def _fail_if_called(*args, **kwargs):
    raise AssertionError("a provider was called")


def _summary(**kwargs):
    return {
        "available": True,
        "overview": "Home office leads.",
        "key_findings": [],
        "risks_and_caveats": [],
        "recommended_next_steps": [],
        "researcher_note": "",
        "model": "openai/gpt-4o-mini",
        "from_run_id": "run_insights_001",
        "generated_at": "2026-10-06T00:00:00+00:00",
        "cached": False,
    }


def _start_live_run(client, monkeypatch, test_settings) -> str:
    study_id = _create_ready_to_run_study(client)
    test_settings.openrouter_api_key = "test-openrouter-key"
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", lambda **kwargs: _mock_insights_run_payload())
    assert client.post(f"/api/v1/studies/{study_id}/simulation-runs").status_code == 200
    return study_id


def test_insights_with_ai_false_never_generate_a_summary_for_a_live_run(client, monkeypatch, test_settings):
    study_id = _start_live_run(client, monkeypatch, test_settings)
    monkeypatch.setattr("src.services.study_service._generate_llm_insights_summary", _fail_if_called)
    monkeypatch.setattr("src.services.study_service._request_llm_insights_summary", _fail_if_called)

    response = client.get(f"/api/v1/studies/{study_id}/insights", params={"ai": "false"})

    assert response.status_code == 200
    insights = response.json()["data"]["insights"]
    assert insights["available"] is True   # the rule-based detailed insights still render
    assert insights["llm_summary"] == {
        "available": False,
        "message": "Demo (no AI) is on: no AI summary was generated. Turn Demo off to get one.",
        "model": None,   # no model wrote anything, so no model chip
        "from_run_id": "run_insights_001",
        "cached": False,
    }
    assert DEMO_SWITCH_NO_AI_SUMMARY == insights["llm_summary"]["message"]


def test_insights_with_ai_false_still_serve_a_summary_already_cached_for_the_run(client, monkeypatch, test_settings):
    study_id = _start_live_run(client, monkeypatch, test_settings)
    calls = {"count": 0}

    def _generate(**kwargs):
        calls["count"] += 1
        return _summary()

    monkeypatch.setattr("src.services.study_service._generate_llm_insights_summary", _generate)
    first = client.get(f"/api/v1/studies/{study_id}/insights", params={"ai": "true"}).json()["data"]["insights"]
    assert first["llm_summary"]["available"] is True and first["llm_summary"]["cached"] is False
    assert calls["count"] == 1

    cached = client.get(f"/api/v1/studies/{study_id}/insights", params={"ai": "false"}).json()["data"]["insights"]
    assert cached["llm_summary"]["available"] is True
    assert cached["llm_summary"]["cached"] is True
    assert cached["llm_summary"]["overview"] == "Home office leads."
    assert calls["count"] == 1   # served from the cache, no new generation


def test_insights_without_the_parameter_generate_a_summary_as_before(client, monkeypatch, test_settings):
    study_id = _start_live_run(client, monkeypatch, test_settings)
    calls = {"count": 0}

    def _generate(**kwargs):
        calls["count"] += 1
        return _summary()

    monkeypatch.setattr("src.services.study_service._generate_llm_insights_summary", _generate)
    insights = client.get(f"/api/v1/studies/{study_id}/insights").json()["data"]["insights"]
    assert insights["llm_summary"]["available"] is True
    assert calls["count"] == 1


def test_insights_on_a_demo_run_keep_the_demo_message_whatever_ai_says(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    monkeypatch.setattr("src.services.study_service.execute_simulation_run", _fail_if_called)
    monkeypatch.setattr("src.services.study_service._generate_llm_insights_summary", _fail_if_called)
    assert client.post(f"/api/v1/studies/{study_id}/simulation-runs", json={"source": "demo"}).status_code == 200

    for ai in ("true", "false"):
        summary = client.get(f"/api/v1/studies/{study_id}/insights", params={"ai": ai}).json()["data"]["insights"]["llm_summary"]
        assert "No AI was called" in summary["message"]
        assert summary["available"] is False


def _drop_cached_interview_insights(client, study_id: str) -> None:
    session = client.app.state.session_factory()
    try:
        study = session.scalar(select(Study).where(Study.public_id == study_id))
        rows = session.scalars(
            select(StudySectionState).where(
                StudySectionState.study_id == study.id,
                StudySectionState.section_key.startswith("interview_insights_"),
            )
        ).all()
        assert rows, "the Neo bootstrap should have cached themes for its interview run"
        for row in rows:
            session.delete(row)
        session.commit()
    finally:
        session.close()


def test_interview_insights_with_ai_false_serve_cached_themes_and_never_extract_new_ones(client, monkeypatch):
    study_id = _bootstrap_neo_study_for_interviews(client, monkeypatch)
    client.app.state.settings.openrouter_api_key = "test-openrouter-key"
    monkeypatch.setattr("src.services.interview_service._call_openrouter_json", _fail_if_called)
    url = f"/api/v1/studies/{study_id}/interview/insights"

    # The Neo interview run comes with seeded themes: ai=false still shows them.
    seeded = client.get(url, params={"ai": "false"}).json()["data"]["interview_insights"]
    assert seeded["available"] is True and seeded["themes"]

    # Without a cached copy, ai=false says why there are no themes and calls no provider.
    _drop_cached_interview_insights(client, study_id)
    response = client.get(url, params={"ai": "false"})
    assert response.status_code == 200
    assert response.json()["data"]["interview_insights"] == {
        "available": False,
        "message": "Demo (no AI) is on: no AI themes were generated. Turn Demo off to get them.",
    }
    assert DEMO_SWITCH_NO_AI_THEMES == response.json()["data"]["interview_insights"]["message"]


def test_interview_insights_without_the_parameter_extract_themes_as_before(client, monkeypatch):
    study_id = _bootstrap_neo_study_for_interviews(client, monkeypatch)
    client.app.state.settings.openrouter_api_key = "test-openrouter-key"
    _drop_cached_interview_insights(client, study_id)
    calls = {"count": 0}

    def _themes(**kwargs):
        calls["count"] += 1
        return json.dumps({"themes": [{"label": "Install speed", "count": 2, "sentiment": "positive", "quote": "Fast."}]})

    monkeypatch.setattr("src.services.interview_service._call_openrouter_json", _themes)
    payload = client.get(f"/api/v1/studies/{study_id}/interview/insights").json()["data"]["interview_insights"]
    assert payload["available"] is True
    assert payload["themes"][0]["label"] == "Install speed"
    assert calls["count"] == 1
