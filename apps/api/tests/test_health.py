from __future__ import annotations

from src.api.app import create_app
from src.config.settings import AppSettings
from src.persistence.base import Base
from src.persistence.session import create_session_factory
from src.schemas.health import HealthCheckResult, HealthPayload
from src.services.health_service import startup_failures
from fastapi.testclient import TestClient


def test_health_endpoint_returns_503_on_failed_status(monkeypatch, client):
    payload = HealthPayload(
        status="failed",
        checks={
            "database": HealthCheckResult(status="fail", message="database down"),
            "artifacts_root": HealthCheckResult(status="ok"),
            "legacy_app_root": HealthCheckResult(status="ok"),
            "python_dependencies": HealthCheckResult(status="ok"),
        },
    )
    monkeypatch.setattr("src.api.health.build_health_payload", lambda settings, session_factory: payload)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["data"]["status"] == "failed"
    assert body["data"]["checks"]["database"]["status"] == "fail"


def test_startup_failures_require_deployment_secret_in_production(test_settings):
    settings = test_settings.model_copy(
        update={
            "app_env": "production",
            "deployment_shared_secret": None,
        }
    )
    session_factory = create_session_factory(settings)

    failures = startup_failures(settings, session_factory)

    assert "deployment_security" in failures


def test_startup_failures_reject_short_deployment_secret_in_production(test_settings):
    settings = test_settings.model_copy(
        update={
            "app_env": "production",
            "app_debug": False,
            "deployment_shared_secret": "short-secret",
        }
    )
    session_factory = create_session_factory(settings)

    failures = startup_failures(settings, session_factory)

    assert "deployment_security" in failures


def test_startup_failures_reject_debug_mode_in_production(test_settings):
    settings = test_settings.model_copy(
        update={
            "app_env": "production",
            "app_debug": True,
            "deployment_shared_secret": "production-shared-secret",
        }
    )
    session_factory = create_session_factory(settings)

    failures = startup_failures(settings, session_factory)

    assert "deployment_security" in failures


def test_non_health_endpoints_require_deployment_secret_when_configured(monkeypatch, test_settings, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir(exist_ok=True)
    settings = AppSettings(
        APP_ENV="production",
        APP_DEBUG=False,
        DATABASE_URL=f"sqlite:///{tmp_path / 'prod.db'}",
        ARTIFACTS_ROOT=artifacts_root,
        LEGACY_APP_ROOT=test_settings.legacy_app_root,
        DEPLOYMENT_SHARED_SECRET="production-shared-secret",
        OPENROUTER_API_KEY="",
        GOOGLE_CLOUD_API_KEY="",
        GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=None,
        GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=None,
        HUD_API_TOKEN="",
        ANTHROPIC_API_KEY="",
        CORS_ALLOW_ORIGINS="https://app.example.com",
    )
    session_factory = create_session_factory(settings)
    Base.metadata.create_all(bind=session_factory.kw["bind"])
    monkeypatch.setattr("src.api.app.startup_failures", lambda settings, sf: [])
    app = create_app(settings)

    with TestClient(app) as client:
        health_response = client.get("/api/v1/health")
        assert health_response.status_code == 200

        blocked_response = client.post("/api/v1/studies", json={})
        assert blocked_response.status_code == 401

        missing_identity_response = client.post(
            "/api/v1/studies",
            json={},
            headers={"X-Deployment-Secret": "production-shared-secret"},
        )
        assert missing_identity_response.status_code == 401

        allowed_response = client.post(
            "/api/v1/studies",
            json={},
            headers={
                "X-Deployment-Secret": "production-shared-secret",
                "X-Authenticated-User-Id": "user_test_owner",
                "X-Authenticated-Auth-Mode": "clerk",
            },
        )
        assert allowed_response.status_code == 200
