"""F-07 (quota): the seeded Neo interview must not spend a day's provider allowance.

`start_interview_run` consumed a daily `interview_run` quota unit before checking the study mode, and
the Neo branch below it returns a pre-built fixture without contacting any provider. So the demo path
charged for work it never did, and a class doing the guided walkthrough could exhaust the day's
interview allowance on canned transcripts before running a live one.

The Custom Study path is genuinely live and must keep paying.
"""

from __future__ import annotations

import pytest

from src.persistence.models import UserUsageCounter
from src.services.usage_limits import METRIC_INTERVIEW_RUN
from sqlalchemy import select


def _interview_units_used(session, owner_user_id: str) -> int:
    rows = session.scalars(
        select(UserUsageCounter).where(
            UserUsageCounter.owner_user_id == owner_user_id,
            UserUsageCounter.metric_key == METRIC_INTERVIEW_RUN,
        )
    ).all()
    return sum(int(row.count or 0) for row in rows)


def _neo_study_ready_for_interviews(client):
    """A Neo study with a persona preview, which is what the interview endpoint requires."""
    created = client.post("/api/v1/studies", json={"study_mode": "neo_smart"}).json()["data"]["study"]
    study_id = created["study_id"]
    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/neo")
    assert response.status_code == 200, response.text
    preview = client.post(
        f"/api/v1/studies/{study_id}/personas/preview",
        json={"sample_size": 2, "use_grounded_priors": True},
    )
    assert preview.status_code == 200, preview.text
    return study_id


def test_the_neo_fixture_interview_charges_no_provider_quota(client, db_session):
    """The fixture makes no provider call, so it must not spend a provider-run unit."""
    settings = client.app.state.settings
    owner = "dev-local-user"
    study_id = _neo_study_ready_for_interviews(client)
    before = _interview_units_used(db_session, owner)

    response = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert response.status_code == 200, response.text

    payload = response.json()["data"]["interview_run"]
    assert payload["demo_fixture"] is True, "this test is only meaningful on the fixture path"

    after = _interview_units_used(db_session, owner)
    assert after == before, (
        f"the seeded fixture consumed {after - before} interview-run unit(s) without calling a provider"
    )


def test_the_neo_fixture_makes_no_provider_call(client, monkeypatch):
    """Guard the premise: if this path ever went live, the quota exemption would be wrong."""
    settings = client.app.state.settings
    settings.openrouter_api_key = "test-openrouter-key"
    study_id = _neo_study_ready_for_interviews(client)

    from src.adapters.legacy_backend.runtime import load_module

    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    def _forbidden(*args, **kwargs):
        raise AssertionError("the seeded Neo interview must not contact a provider")

    monkeypatch.setattr(llm_client.requests, "post", _forbidden)

    response = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["interview_run"]["demo_fixture"] is True
