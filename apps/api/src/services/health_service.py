from __future__ import annotations

import importlib
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from src.config.settings import AppSettings
from src.schemas.health import HealthCheckResult, HealthPayload


REQUIRED_PRIOR_FILES = [
    "age_income_priors.parquet",
    "ownership_home_type_priors.parquet",
    "household_size_priors.parquet",
    "work_mode_hints.parquet",
]

REQUIRED_LOOKUP_FILES = [
    "hud_zip_cbsa_lookup.parquet",
    "hud_zip_county_lookup.parquet",
]


def startup_failures(settings: AppSettings, session_factory: sessionmaker) -> List[str]:
    payload = build_health_payload(settings, session_factory)
    return [name for name, check in payload.checks.items() if check.status == "fail" and name in HARD_FAIL_CHECKS]


HARD_FAIL_CHECKS = {"database", "artifacts_root", "legacy_app_root", "python_dependencies", "deployment_security"}


def build_health_payload(settings: AppSettings, session_factory: sessionmaker) -> HealthPayload:
    checks: Dict[str, HealthCheckResult] = {}

    checks["database"] = _database_check(session_factory)
    checks["artifacts_root"] = _artifacts_root_check(settings.artifacts_root)
    checks["legacy_app_root"] = _legacy_root_check(settings.legacy_app_root)
    checks["python_dependencies"] = _python_dependency_check()
    checks["deployment_security"] = _deployment_security_check(settings)
    checks["openrouter"] = _openrouter_check(settings)
    checks["google_vision"] = _google_vision_check(settings)
    checks["grounding_priors"] = _grounding_priors_check(settings.legacy_app_root)
    checks["hud_lookups"] = _hud_lookups_check(settings.legacy_app_root, settings.hud_api_token)

    status = "ok"
    if any(check.status == "fail" for name, check in checks.items() if name in HARD_FAIL_CHECKS):
        status = "failed"
    elif any(check.status == "warn" for check in checks.values()):
        status = "degraded"

    return HealthPayload(status=status, checks=checks)


def _database_check(session_factory: sessionmaker) -> HealthCheckResult:
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return HealthCheckResult(status="ok")
    except Exception as exc:
        return HealthCheckResult(status="fail", message=str(exc))


def _artifacts_root_check(path: Path) -> HealthCheckResult:
    if not path.exists():
        return HealthCheckResult(status="fail", message="ARTIFACTS_ROOT does not exist.")
    if not path.is_dir():
        return HealthCheckResult(status="fail", message="ARTIFACTS_ROOT is not a directory.")
    try:
        probe = path / ".write_probe"
        probe.write_text("ok")
        probe.unlink()
        return HealthCheckResult(status="ok")
    except Exception as exc:
        return HealthCheckResult(status="fail", message=f"ARTIFACTS_ROOT is not writable: {exc}")


def _legacy_root_check(path: Path) -> HealthCheckResult:
    if not path.exists():
        return HealthCheckResult(status="fail", message="LEGACY_APP_ROOT does not exist.")
    if not path.is_dir():
        return HealthCheckResult(status="fail", message="LEGACY_APP_ROOT is not a directory.")
    if not (path / "backend").exists():
        return HealthCheckResult(status="fail", message="LEGACY_APP_ROOT does not contain backend/.")
    return HealthCheckResult(status="ok")


def _python_dependency_check() -> HealthCheckResult:
    required = {
        "pydantic": "pydantic",
        "requests": "requests",
        "docx": "python-docx",
        "pypdf": "pypdf",
        "pandas": "pandas",
        "sqlalchemy": "sqlalchemy",
    }
    missing = []
    for module_name, package_name in required.items():
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(package_name)
    if missing:
        return HealthCheckResult(status="fail", message="Missing required Python dependencies.", details={"missing": missing})
    return HealthCheckResult(status="ok")


def _deployment_security_check(settings: AppSettings) -> HealthCheckResult:
    if not settings.enforce_deployment_guardrails:
        return HealthCheckResult(status="ok")
    secret = (settings.deployment_shared_secret or "").strip()
    if not secret:
        return HealthCheckResult(
            status="fail",
            message="DEPLOYMENT_SHARED_SECRET must be configured outside local/test environments.",
        )
    if len(secret) < 16:
        return HealthCheckResult(
            status="fail",
            message="DEPLOYMENT_SHARED_SECRET must be at least 16 characters outside local/test environments.",
        )
    if settings.app_debug:
        return HealthCheckResult(
            status="fail",
            message="APP_DEBUG must be false outside local/test environments.",
        )
    return HealthCheckResult(status="ok")


def _openrouter_check(settings: AppSettings) -> HealthCheckResult:
    if settings.openrouter_api_key:
        return HealthCheckResult(status="ok")
    return HealthCheckResult(status="warn", message="OPENROUTER_API_KEY missing.")


def _google_vision_check(settings: AppSettings) -> HealthCheckResult:
    if settings.google_cloud_api_key:
        return HealthCheckResult(status="ok")
    has_service_account_path = bool(
        settings.google_cloud_service_account_path
        and str(settings.google_cloud_service_account_path) not in {"", "."}
        and settings.google_cloud_service_account_path.exists()
        and settings.google_cloud_service_account_path.is_file()
    )
    if settings.google_cloud_service_account_json or has_service_account_path:
        try:
            importlib.import_module("cryptography")
            return HealthCheckResult(status="ok")
        except Exception:
            return HealthCheckResult(status="warn", message="Service-account auth configured but cryptography is unavailable.")
    return HealthCheckResult(status="warn", message="Google Vision credentials missing.")


def _grounding_priors_check(legacy_root: Path) -> HealthCheckResult:
    priors_dir = legacy_root / "data" / "processed" / "priors"
    missing = [name for name in REQUIRED_PRIOR_FILES if not (priors_dir / name).exists()]
    if missing:
        return HealthCheckResult(status="warn", message="Grounding prior files missing; persona preview will degrade.", details={"missing": missing})
    return HealthCheckResult(status="ok")


def _hud_lookups_check(legacy_root: Path, hud_api_token: Optional[str]) -> HealthCheckResult:
    lookups_dir = legacy_root / "data" / "processed" / "lookups"
    missing = [name for name in REQUIRED_LOOKUP_FILES if not (lookups_dir / name).exists()]
    if not missing:
        return HealthCheckResult(status="ok")
    if hud_api_token:
        return HealthCheckResult(status="warn", message="Local HUD lookups missing; API fallback will be used.", details={"missing": missing})
    return HealthCheckResult(status="warn", message="Local HUD lookups missing and HUD_API_TOKEN not configured.", details={"missing": missing})
