from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]


def _resolve_runtime_path(path: Path, *, base_dir: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _looks_like_legacy_root(path: Path) -> bool:
    return path.exists() and path.is_dir() and (path / "backend").exists()


def _resolve_legacy_root(path: Path) -> Path:
    primary = _resolve_runtime_path(path, base_dir=API_ROOT)
    if _looks_like_legacy_root(primary):
        return primary

    fallback_candidates = (
        REPO_ROOT / "NeoSmart-Hackathon-App",
        REPO_ROOT.parent / "NeoSmart-Hackathon-App",
    )
    for candidate in fallback_candidates:
        resolved = candidate.resolve()
        if _looks_like_legacy_root(resolved):
            return resolved

    return primary


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
    cors_allow_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ALLOW_ORIGINS",
    )

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def resolve_paths(self) -> "AppSettings":
        self.artifacts_root = _resolve_runtime_path(self.artifacts_root, base_dir=API_ROOT)
        self.legacy_app_root = _resolve_legacy_root(self.legacy_app_root)
        return self

    @property
    def cors_allow_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
