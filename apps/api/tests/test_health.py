from __future__ import annotations

from pathlib import Path

from src.config.settings import AppSettings
from src.schemas.health import HealthCheckResult, HealthPayload


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


def test_settings_resolve_relative_paths_and_fallback_legacy_root():
    workspace_root = Path(__file__).resolve().parents[3]
    legacy_candidates = (
        workspace_root / "NeoSmart-Hackathon-App",
        workspace_root.parent / "NeoSmart-Hackathon-App",
    )
    expected_legacy_root = next(candidate for candidate in legacy_candidates if (candidate / "backend").exists())

    settings = AppSettings(
        APP_ENV="test",
        APP_DEBUG=True,
        DATABASE_URL="sqlite:///./test.db",
        ARTIFACTS_ROOT="artifacts",
        LEGACY_APP_ROOT="./missing-legacy-root",
        OPENROUTER_API_KEY="",
        GOOGLE_CLOUD_API_KEY="",
        GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=None,
        GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=None,
        HUD_API_TOKEN="",
        ANTHROPIC_API_KEY="",
    )

    assert settings.artifacts_root == (workspace_root / "apps" / "api" / "artifacts").resolve()
    assert settings.legacy_app_root == expected_legacy_root.resolve()
