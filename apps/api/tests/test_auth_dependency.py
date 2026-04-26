from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth import AuthUser, get_current_user
from src.api.errors import install_exception_handlers
from src.config.settings import AppSettings


def _build_prod_settings(tmp_path: Path) -> AppSettings:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir(exist_ok=True)
    return AppSettings(
        APP_ENV="production",
        APP_DEBUG=False,
        DATABASE_URL=f"sqlite:///{tmp_path / 'auth.db'}",
        ARTIFACTS_ROOT=artifacts_root,
        LEGACY_APP_ROOT=tmp_path,
        DEPLOYMENT_SHARED_SECRET="deployment-shared-secret-123",
        OPENROUTER_API_KEY="",
        GOOGLE_CLOUD_API_KEY="",
        GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=None,
        GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=None,
        HUD_API_TOKEN="",
        ANTHROPIC_API_KEY="",
        CORS_ALLOW_ORIGINS="https://app.example.com",
        ADMIN_CLERK_USER_IDS="user_admin_one, user_admin_two",
    )


def _build_app(settings: AppSettings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings

    install_exception_handlers(app)

    @app.get("/whoami")
    def whoami(current_user: AuthUser = Depends(get_current_user)):
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "auth_mode": current_user.auth_mode,
            "is_admin": current_user.is_admin,
        }

    return app


def test_missing_identity_headers_return_401(tmp_path):
    settings = _build_prod_settings(tmp_path)
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get("/whoami")

        assert response.status_code == 401
        body = response.json()
        assert body["error"]["code"] == "unauthorized"


def test_valid_clerk_headers_resolve_to_auth_user(tmp_path):
    settings = _build_prod_settings(tmp_path)
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get(
            "/whoami",
            headers={
                "X-Authenticated-User-Id": "user_regular",
                "X-Authenticated-User-Email": "regular@example.com",
                "X-Authenticated-Auth-Mode": "clerk",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == "user_regular"
        assert body["email"] == "regular@example.com"
        assert body["auth_mode"] == "clerk"
        assert body["is_admin"] is False


def test_admin_clerk_user_ids_are_honored(tmp_path):
    settings = _build_prod_settings(tmp_path)
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get(
            "/whoami",
            headers={
                "X-Authenticated-User-Id": "user_admin_one",
                "X-Authenticated-Auth-Mode": "clerk",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_admin"] is True


def test_dev_fallback_user_resolves_in_non_production(tmp_path):
    settings = AppSettings(
        APP_ENV="test",
        APP_DEBUG=True,
        DATABASE_URL=f"sqlite:///{tmp_path / 'auth.db'}",
        ARTIFACTS_ROOT=tmp_path,
        LEGACY_APP_ROOT=tmp_path,
        OPENROUTER_API_KEY="",
        GOOGLE_CLOUD_API_KEY="",
        GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=None,
        GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=None,
        HUD_API_TOKEN="",
        ANTHROPIC_API_KEY="",
    )
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get("/whoami")

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == "dev-local-user"
        assert body["auth_mode"] == "dev-fallback"
        assert body["is_admin"] is True


def test_legacy_shared_password_mode_returns_legacy_user(tmp_path):
    settings = _build_prod_settings(tmp_path)
    app = _build_app(settings)

    with TestClient(app) as client:
        response = client.get(
            "/whoami",
            headers={"X-Authenticated-Auth-Mode": "legacy-shared-password"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["auth_mode"] == "legacy-shared-password"
        assert body["user_id"].startswith("legacy:")
        assert body["is_admin"] is True


def test_cross_user_studies_are_isolated(tmp_path, monkeypatch):
    """Create a study as user A, verify user B cannot access it."""
    from src.api.app import create_app
    from src.persistence.base import Base
    from src.persistence.session import create_session_factory

    settings = _build_prod_settings(tmp_path)
    session_factory = create_session_factory(settings)
    Base.metadata.create_all(bind=session_factory.kw["bind"])

    monkeypatch.setattr("src.api.app.startup_failures", lambda *_args, **_kwargs: [])
    app = create_app(settings)

    user_a_headers = {
        "X-Deployment-Secret": "deployment-shared-secret-123",
        "X-Authenticated-User-Id": "user_alpha",
        "X-Authenticated-Auth-Mode": "clerk",
    }
    user_b_headers = {
        "X-Deployment-Secret": "deployment-shared-secret-123",
        "X-Authenticated-User-Id": "user_beta",
        "X-Authenticated-Auth-Mode": "clerk",
    }

    with TestClient(app) as client:
        create_response = client.post("/api/v1/studies", json={}, headers=user_a_headers)
        assert create_response.status_code == 200
        study_id = create_response.json()["data"]["study"]["study_id"]

        # Owner can read.
        owner_read = client.get(f"/api/v1/studies/{study_id}", headers=user_a_headers)
        assert owner_read.status_code == 200

        # Another user sees a 403.
        other_read = client.get(f"/api/v1/studies/{study_id}", headers=user_b_headers)
        assert other_read.status_code == 403
        assert other_read.json()["error"]["code"] == "forbidden"

        # Admin can read.
        admin_read = client.get(
            f"/api/v1/studies/{study_id}",
            headers={
                "X-Deployment-Secret": "deployment-shared-secret-123",
                "X-Authenticated-User-Id": "user_admin_one",
                "X-Authenticated-Auth-Mode": "clerk",
            },
        )
        assert admin_read.status_code == 200
