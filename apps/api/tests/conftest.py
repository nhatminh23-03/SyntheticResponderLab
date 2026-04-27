from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


API_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.api.app import create_app
from src.config.settings import AppSettings
from src.persistence.base import Base
from src.persistence.session import create_session_factory


@pytest.fixture
def test_settings(tmp_path: Path) -> AppSettings:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    database_path = tmp_path / "test.db"
    return AppSettings(
        APP_ENV="test",
        APP_DEBUG=True,
        DATABASE_URL=f"sqlite:///{database_path}",
        ARTIFACTS_ROOT=artifacts_root,
        LEGACY_APP_ROOT=WORKSPACE_ROOT / "NeoSmart-Hackathon-App",
        OPENROUTER_API_KEY="",
        GOOGLE_CLOUD_API_KEY="",
        GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON=None,
        GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH=None,
        HUD_API_TOKEN="",
        ANTHROPIC_API_KEY="",
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
