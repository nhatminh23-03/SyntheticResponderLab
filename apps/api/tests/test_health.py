from __future__ import annotations

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

