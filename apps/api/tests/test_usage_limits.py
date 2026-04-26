from __future__ import annotations

from datetime import date

from sqlalchemy import select

from src.persistence.models import Job, Study, UserUsageCounter
from src.services.usage_limits import (
    METRIC_INTERVIEW_RUN,
    METRIC_PRODUCT_IMAGE_ANALYSIS,
    METRIC_SIMULATION_RUN,
    METRIC_STABILITY_CHECK,
    METRIC_STUDY_CREATE,
    METRIC_SURVEY_UPLOAD,
    consume_daily_quota,
)


def _create_ready_to_run_study(client, study_mode: str = "neo_smart") -> str:
    created = client.post("/api/v1/studies", json={"study_mode": study_mode}).json()["data"]["study"]
    study_id = created["study_id"]

    audience_response = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={
            "state": "California",
            "age_min": 30,
            "age_max": 60,
            "homeowner_only": True,
        },
    )
    assert audience_response.status_code == 200

    preset_response = client.post(f"/api/v1/studies/{study_id}/survey/preset/neo")
    assert preset_response.status_code == 200

    experiment_response = client.patch(
        f"/api/v1/studies/{study_id}/experiment",
        json={
            "sample_size": 24,
            "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "reruns_per_persona": 1,
        },
    )
    assert experiment_response.status_code == 200

    return study_id


def _bootstrap_neo_study_for_interviews(client, monkeypatch) -> str:
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    monkeypatch.setattr(
        "src.services.study_service.preview_personas",
        lambda **kwargs: {
            "generation_mode": "grounded_priors",
            "grounded_priors_available": True,
            "cex_affordability_available": True,
            "prior_notes": [{"note": "Grounded priors active"}],
            "personas": [
                {
                    "persona_id": "neo-001",
                    "segment_label": "Backyard office homeowners",
                    "fit_tier": "strong",
                }
            ],
        },
    )

    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/neo")
    assert response.status_code == 200
    return study_id


def _usage_rows(client):
    session = client.app.state.session_factory()
    try:
        return session.scalars(select(UserUsageCounter)).all()
    finally:
        session.close()


def test_daily_usage_counters_bucket_by_utc_day(db_session, test_settings, monkeypatch):
    monkeypatch.setattr("src.services.usage_limits.utc_today", lambda: date(2026, 4, 26))
    consume_daily_quota(
        db_session,
        test_settings,
        owner_user_id="user_demo",
        metric_key=METRIC_STUDY_CREATE,
    )
    db_session.commit()

    monkeypatch.setattr("src.services.usage_limits.utc_today", lambda: date(2026, 4, 27))
    consume_daily_quota(
        db_session,
        test_settings,
        owner_user_id="user_demo",
        metric_key=METRIC_STUDY_CREATE,
    )
    db_session.commit()

    rows = db_session.scalars(
        select(UserUsageCounter).order_by(UserUsageCounter.bucket_date_utc.asc())
    ).all()
    assert len(rows) == 2
    assert rows[0].bucket_date_utc == date(2026, 4, 26)
    assert rows[1].bucket_date_utc == date(2026, 4, 27)


def test_provider_metrics_share_provider_limit_bucket(test_settings, db_session):
    consume_daily_quota(
        db_session,
        test_settings,
        owner_user_id="user_demo",
        metric_key=METRIC_SIMULATION_RUN,
    )
    consume_daily_quota(
        db_session,
        test_settings,
        owner_user_id="user_demo",
        metric_key=METRIC_STABILITY_CHECK,
    )
    consume_daily_quota(
        db_session,
        test_settings,
        owner_user_id="user_demo",
        metric_key=METRIC_INTERVIEW_RUN,
    )
    db_session.commit()

    rows = db_session.scalars(
        select(UserUsageCounter).where(UserUsageCounter.owner_user_id == "user_demo")
    ).all()
    assert {row.metric_key for row in rows} == {
        METRIC_SIMULATION_RUN,
        METRIC_STABILITY_CHECK,
        METRIC_INTERVIEW_RUN,
    }
    assert all(row.count == 1 for row in rows)


def test_create_study_limit_blocks_even_dev_admin_fallback(client):
    client.app.state.settings.daily_study_create_limit = 1

    first = client.post("/api/v1/studies", json={})
    assert first.status_code == 200

    second = client.post("/api/v1/studies", json={})
    assert second.status_code == 429
    payload = second.json()["error"]
    assert payload["code"] == "quota_exceeded"
    assert "study creation limit" in payload["message"]

    rows = _usage_rows(client)
    assert len(rows) == 1
    assert rows[0].metric_key == METRIC_STUDY_CREATE
    assert rows[0].count == 1


def test_survey_upload_counts_against_daily_upload_limit(client, monkeypatch):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.app.state.settings.daily_upload_limit = 1

    monkeypatch.setattr(
        "src.services.study_service.parse_normalize_validate_survey",
        lambda filename, file_bytes, legacy_app_root: {
            "survey_title": "Demo survey",
            "description": None,
            "source_format": "md",
            "parse_warnings": [],
            "questions": [
                {
                    "id": "Q1",
                    "text": "How interested are you?",
                    "question_type": "single_choice",
                    "options": ["A", "B"],
                }
            ],
        },
    )

    first = client.post(
        f"/api/v1/studies/{study_id}/survey/upload",
        files={"file": ("survey.md", b"# demo", "text/markdown")},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/studies/{study_id}/survey/upload",
        files={"file": ("survey.md", b"# demo", "text/markdown")},
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "quota_exceeded"
    assert "upload limit" in second.json()["error"]["message"]

    rows = _usage_rows(client)
    upload_rows = [row for row in rows if row.metric_key == METRIC_SURVEY_UPLOAD]
    assert len(upload_rows) == 1
    assert upload_rows[0].count == 1


def test_product_image_analysis_counts_against_daily_upload_limit(client, monkeypatch):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.app.state.settings.daily_upload_limit = 1

    monkeypatch.setattr(
        "src.services.study_service.product_image_analysis",
        lambda **kwargs: {
            "analysis": {"labels": ["studio"]},
            "product_patch": {"product_name": "Updated Name"},
        },
    )

    first = client.post(
        f"/api/v1/studies/{study_id}/product/image-analysis",
        files={"file": ("product.png", b"\x89PNG\r\n\x1a\nsmall", "image/png")},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/studies/{study_id}/product/image-analysis",
        files={"file": ("product.png", b"\x89PNG\r\n\x1a\nsmall", "image/png")},
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "quota_exceeded"

    rows = _usage_rows(client)
    upload_rows = [row for row in rows if row.metric_key == METRIC_PRODUCT_IMAGE_ANALYSIS]
    assert len(upload_rows) == 1
    assert upload_rows[0].count == 1


def test_simulation_run_counts_against_daily_provider_limit(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    client.app.state.settings.daily_provider_run_limit = 1

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: {
            "run_id": "run_demo_001",
            "status": "completed",
            "total_requested_responses": 24,
            "total_generated_responses": 24,
            "models_used": ["openai/gpt-4o-mini"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 32,
            "generation_mode": "mock",
            "personas": [],
            "response_record_preview": [],
            "response_records": [],
            "warnings": [],
            "survey_parse_warnings": [],
        },
    )

    first = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert first.status_code == 200

    second = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "quota_exceeded"
    assert "run limit" in second.json()["error"]["message"]

    rows = _usage_rows(client)
    provider_rows = [row for row in rows if row.metric_key == METRIC_SIMULATION_RUN]
    assert len(provider_rows) == 1
    assert provider_rows[0].count == 1


def test_stability_check_counts_against_daily_provider_limit(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    client.app.state.settings.daily_provider_run_limit = 1

    monkeypatch.setattr(
        "src.services.study_service.execute_stability_check",
        lambda **kwargs: {
            "status": "completed",
            "repeat_runs": kwargs["repeat_runs"],
            "stability_table": [],
            "stability_labels": [],
        },
    )

    first = client.post(
        f"/api/v1/studies/{study_id}/simulation-runs/stability",
        json={"repeat_runs": 2},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/studies/{study_id}/simulation-runs/stability",
        json={"repeat_runs": 2},
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "quota_exceeded"


def test_interview_run_counts_against_daily_provider_limit(client, monkeypatch):
    study_id = _bootstrap_neo_study_for_interviews(client, monkeypatch)
    client.app.state.settings.daily_provider_run_limit = 1

    first = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert first.status_code == 200

    second = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "quota_exceeded"


def test_in_flight_provider_job_blocks_second_start(client):
    study_id = _create_ready_to_run_study(client)
    session = client.app.state.session_factory()
    try:
        study = session.scalar(select(Study).where(Study.public_id == study_id))
        assert study is not None
        session.add(
            Job(
                public_id="job_inflight_001",
                study_id=study.id,
                job_type="simulation_run",
                status="running",
                payload_json={},
                result_json=None,
                error_json=None,
            )
        )
        session.commit()
    finally:
        session.close()

    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 409
    payload = response.json()["error"]
    assert payload["code"] == "provider_run_in_flight"
    assert "run in progress" in payload["message"]


def test_completed_or_failed_jobs_do_not_block_future_provider_runs(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    session = client.app.state.session_factory()
    try:
        study = session.scalar(select(Study).where(Study.public_id == study_id))
        assert study is not None
        session.add(
            Job(
                public_id="job_completed_001",
                study_id=study.id,
                job_type="simulation_run",
                status="completed",
                payload_json={},
                result_json={"run_id": "old_completed"},
                error_json=None,
            )
        )
        session.add(
            Job(
                public_id="job_failed_001",
                study_id=study.id,
                job_type="interview_run",
                status="failed",
                payload_json={},
                result_json=None,
                error_json={"message": "old failure"},
            )
        )
        session.commit()
    finally:
        session.close()

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: {
            "run_id": "run_after_old_jobs",
            "status": "completed",
            "total_requested_responses": 24,
            "total_generated_responses": 24,
            "models_used": ["openai/gpt-4o-mini"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 32,
            "generation_mode": "mock",
            "personas": [],
            "response_record_preview": [],
            "response_records": [],
            "warnings": [],
            "survey_parse_warnings": [],
        },
    )

    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert response.status_code == 200
    assert response.json()["data"]["simulation_run"]["result"]["run_id"] == "run_after_old_jobs"
