"""Centralized settings for the Grounded Synthetic Respondent Lab scaffold.

This module keeps paths and key environment variable names in one place so
future modules can import settings without hardcoded strings.
"""

from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    """Application settings container.

    Notes:
    - This is intentionally minimal for hackathon scaffolding.
    - Environment variable values are not read here yet; only the canonical
      variable names are defined.
    """

    app_name: str = "Grounded Synthetic Respondent Lab"
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])

    data_dirs: Dict[str, Path] = Field(default_factory=dict)
    api_key_env_vars: Dict[str, str] = Field(
        default_factory=lambda: {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "together": "TOGETHER_API_KEY",
        }
    )
    default_paths: Dict[str, Path] = Field(default_factory=dict)


def get_settings() -> AppSettings:
    """Build and return default settings used across the project."""
    root = Path(__file__).resolve().parents[1]

    data_dirs = {
        "raw": root / "data" / "raw",
        "processed": root / "data" / "processed",
        "runs": root / "data" / "processed" / "runs",
        "analysis": root / "data" / "processed" / "analysis",
        "exports": root / "data" / "processed" / "exports",
    }

    default_paths = {
        "survey_upload_dir": root / "data" / "processed" / "runs",
        "persona_cache": root / "data" / "processed" / "priors" / "persona_cache.json",
        "latest_run_manifest": root / "data" / "processed" / "runs" / "latest_run_manifest.json",
    }

    return AppSettings(data_dirs=data_dirs, default_paths=default_paths)


settings = get_settings()
