from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config.settings import API_ROOT, AppSettings


def test_settings_resolve_relative_paths():
    settings = AppSettings(
        APP_ENV="development",
        APP_DEBUG=True,
        DATABASE_URL="sqlite:///./local-dev.db",
        ARTIFACTS_ROOT="./artifacts",
        LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
    )

    assert settings.artifacts_root == (API_ROOT / "artifacts").resolve()
    assert settings.legacy_app_root == (API_ROOT / "../../NeoSmart-Hackathon-App").resolve()


def test_settings_reject_invalid_database_url():
    with pytest.raises(ValidationError, match="DATABASE_URL is invalid"):
        AppSettings(
            APP_ENV="development",
            APP_DEBUG=True,
            DATABASE_URL="not-a-valid-db-url",
            ARTIFACTS_ROOT="./artifacts",
            LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
        )


def test_settings_reject_non_positive_upload_limits():
    with pytest.raises(ValidationError, match="Configured limits must be positive integers"):
        AppSettings(
            APP_ENV="development",
            APP_DEBUG=True,
            DATABASE_URL="sqlite:///./local-dev.db",
            ARTIFACTS_ROOT="./artifacts",
            LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
            MAX_SURVEY_UPLOAD_BYTES=0,
        )
