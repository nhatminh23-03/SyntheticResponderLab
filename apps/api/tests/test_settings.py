from __future__ import annotations

from decimal import Decimal

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


@pytest.mark.parametrize("cache_mode", ["cache_first", "replay_only", "off"])
def test_settings_accept_cache_modes(cache_mode):
    settings = AppSettings(
        APP_ENV="development",
        APP_DEBUG=True,
        DATABASE_URL="sqlite:///./local-dev.db",
        ARTIFACTS_ROOT="./artifacts",
        LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
        CACHE_MODE=cache_mode.upper(),
    )

    assert settings.cache_mode == cache_mode


def test_settings_default_cache_mode_is_cache_first():
    settings = AppSettings(
        APP_ENV="development",
        APP_DEBUG=True,
        DATABASE_URL="sqlite:///./local-dev.db",
        ARTIFACTS_ROOT="./artifacts",
        LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
    )

    assert settings.cache_mode == "cache_first"


def test_settings_reject_unknown_cache_mode():
    with pytest.raises(ValidationError, match="CACHE_MODE must be one of"):
        AppSettings(
            APP_ENV="development",
            APP_DEBUG=True,
            DATABASE_URL="sqlite:///./local-dev.db",
            ARTIFACTS_ROOT="./artifacts",
            LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
            CACHE_MODE="sometimes",
        )


def test_settings_supports_budget_default_override_and_zero_kill_switch(monkeypatch):
    common = {
        "APP_ENV": "development",
        "APP_DEBUG": True,
        "DATABASE_URL": "sqlite:///./local-dev.db",
        "ARTIFACTS_ROOT": "./artifacts",
        "LEGACY_APP_ROOT": "../../NeoSmart-Hackathon-App",
    }
    assert AppSettings(**common).llm_budget_usd == Decimal("0.75")

    monkeypatch.setenv("NEO_LLM_BUDGET_USD", "0")
    assert AppSettings(**common).llm_budget_usd == Decimal("0")

    monkeypatch.setenv("NEO_LLM_BUDGET_USD", "1.25")
    assert AppSettings(**common).llm_budget_usd == Decimal("1.25")


def test_settings_rejects_invalid_budget_override(monkeypatch):
    monkeypatch.setenv("NEO_LLM_BUDGET_USD", "unlimited")

    with pytest.raises(ValidationError, match="NEO_LLM_BUDGET_USD must be"):
        AppSettings(
            APP_ENV="development",
            APP_DEBUG=True,
            DATABASE_URL="sqlite:///./local-dev.db",
            ARTIFACTS_ROOT="./artifacts",
            LEGACY_APP_ROOT="../../NeoSmart-Hackathon-App",
        )
