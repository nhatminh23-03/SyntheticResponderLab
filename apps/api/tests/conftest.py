from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


API_ROOT = Path(__file__).resolve().parents[1]

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.api.app import create_app
from src.config.settings import AppSettings
from src.persistence.base import Base
from src.persistence.session import create_session_factory


@pytest.fixture(autouse=True)
def isolate_app_settings_environment(monkeypatch: pytest.MonkeyPatch):
    """Keep developer/deployment settings from changing test behavior."""
    setting_names = {name.lower() for name in AppSettings.model_fields}
    setting_names.update(
        str(field.alias).lower()
        for field in AppSettings.model_fields.values()
        if field.alias
    )
    for env_name in tuple(os.environ):
        if env_name.lower() in setting_names:
            monkeypatch.delenv(env_name)
    monkeypatch.setitem(AppSettings.model_config, "env_file", None)


@pytest.fixture
def test_settings(tmp_path: Path) -> AppSettings:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    database_path = tmp_path / "test.db"
    return AppSettings(
        _env_file=None,
        APP_ENV="test",
        APP_DEBUG=True,
        DATABASE_URL=f"sqlite:///{database_path}",
        ARTIFACTS_ROOT=artifacts_root,
        LEGACY_APP_ROOT=API_ROOT / "legacy_runtime",
        OPENROUTER_API_KEY="",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        GOOGLE_CLOUD_API_KEY="",
        GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=None,
        GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=None,
        HUD_API_TOKEN="",
        ANTHROPIC_API_KEY="",
        DEPLOYMENT_SHARED_SECRET=None,
        CORS_ALLOW_ORIGINS="http://localhost:3000,http://127.0.0.1:3000",
        MAX_SURVEY_UPLOAD_BYTES=8 * 1024 * 1024,
        MAX_PRODUCT_IMAGE_UPLOAD_BYTES=5 * 1024 * 1024,
        DAILY_STUDY_CREATE_LIMIT=20,
        DAILY_UPLOAD_LIMIT=50,
        DAILY_PROVIDER_RUN_LIMIT=20,
        ADMIN_CLERK_USER_IDS="",
        REQUIRE_AUTHENTICATED_IDENTITY=False,
        DEV_FALLBACK_USER_ID="dev-local-user",
    )


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, test_settings: AppSettings):
    session_factory = create_session_factory(test_settings)
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("src.api.app.startup_failures", lambda settings, sf: [])
    return create_app(test_settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(test_settings: AppSettings):
    session_factory = create_session_factory(test_settings)
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
