from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

API_ROOT = Path(__file__).resolve().parents[2]


class AppSettings(BaseSettings):
    app_env: str = Field(alias="APP_ENV")
    app_debug: bool = Field(alias="APP_DEBUG")
    database_url: str = Field(alias="DATABASE_URL")
    artifacts_root: Path = Field(alias="ARTIFACTS_ROOT")
    legacy_app_root: Path = Field(alias="LEGACY_APP_ROOT")

    openrouter_api_key: Optional[str] = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")

    google_cloud_api_key: Optional[str] = Field(default=None, alias="GOOGLE_CLOUD_API_KEY")
    google_cloud_service_account_json: Optional[str] = Field(default=None, alias="GOOGLE_CLOUD_SERVICE_ACCOUNT_JSON")
    google_cloud_service_account_path: Optional[Path] = Field(default=None, alias="GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH")

    hud_api_token: Optional[str] = Field(default=None, alias="HUD_API_TOKEN")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    deployment_shared_secret: Optional[str] = Field(default=None, alias="DEPLOYMENT_SHARED_SECRET")
    cors_allow_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ALLOW_ORIGINS",
    )
    max_survey_upload_bytes: int = Field(default=8 * 1024 * 1024, alias="MAX_SURVEY_UPLOAD_BYTES")
    max_product_image_upload_bytes: int = Field(
        default=5 * 1024 * 1024,
        alias="MAX_PRODUCT_IMAGE_UPLOAD_BYTES",
    )
    daily_study_create_limit: int = Field(default=20, alias="DAILY_STUDY_CREATE_LIMIT")
    daily_upload_limit: int = Field(default=50, alias="DAILY_UPLOAD_LIMIT")
    daily_provider_run_limit: int = Field(default=20, alias="DAILY_PROVIDER_RUN_LIMIT")
    admin_clerk_user_ids: str = Field(default="", alias="ADMIN_CLERK_USER_IDS")
    require_authenticated_identity: bool = Field(
        default=False,
        alias="REQUIRE_AUTHENTICATED_IDENTITY",
    )
    dev_fallback_user_id: str = Field(
        default="dev-local-user",
        alias="DEV_FALLBACK_USER_ID",
    )

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=API_ROOT / ".env",
        case_sensitive=False,
    )

    @field_validator("artifacts_root", "legacy_app_root", mode="before")
    @classmethod
    def _resolve_paths(cls, value: str | Path) -> Path:
        if not str(value).strip():
            raise ValueError("Path value cannot be empty.")
        path = Path(value)
        if path.is_absolute():
            return path
        return (API_ROOT / path).resolve()

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not normalized:
            raise ValueError("APP_ENV cannot be empty.")
        return normalized

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("DATABASE_URL cannot be empty.")
        try:
            make_url(trimmed)
        except Exception as exc:
            raise ValueError(f"DATABASE_URL is invalid: {exc}") from exc
        return trimmed

    @field_validator(
        "max_survey_upload_bytes",
        "max_product_image_upload_bytes",
        "daily_study_create_limit",
        "daily_upload_limit",
        "daily_provider_run_limit",
    )
    @classmethod
    def _validate_positive_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Configured limits must be positive integers.")
        return value

    @property
    def cors_allow_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]

    @property
    def enforce_deployment_guardrails(self) -> bool:
        return self.app_env not in {"development", "dev", "test", "local"}

    @property
    def admin_clerk_user_id_set(self) -> set[str]:
        return {
            entry.strip()
            for entry in self.admin_clerk_user_ids.split(",")
            if entry.strip()
        }

    @property
    def enforce_per_user_identity(self) -> bool:
        if self.require_authenticated_identity:
            return True
        return self.enforce_deployment_guardrails


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
