from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request

from src.api.dependencies import get_settings
from src.config.settings import AppSettings
from src.services.exceptions import UnauthorizedApiError


AUTH_HEADER_USER_ID = "x-authenticated-user-id"
AUTH_HEADER_USER_EMAIL = "x-authenticated-user-email"
AUTH_HEADER_AUTH_MODE = "x-authenticated-auth-mode"

AUTH_MODE_CLERK = "clerk"
AUTH_MODE_LEGACY = "legacy-shared-password"


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: Optional[str]
    auth_mode: str
    is_admin: bool

    @property
    def is_dev_fallback(self) -> bool:
        return self.auth_mode == "dev-fallback"


def _extract_header(request: Request, name: str) -> Optional[str]:
    value = request.headers.get(name)
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def resolve_current_user(
    request: Request,
    settings: AppSettings,
) -> Optional[AuthUser]:
    user_id = _extract_header(request, AUTH_HEADER_USER_ID)
    auth_mode = _extract_header(request, AUTH_HEADER_AUTH_MODE)
    email = _extract_header(request, AUTH_HEADER_USER_EMAIL)

    if user_id:
        normalized_mode = auth_mode or AUTH_MODE_CLERK
        is_admin = user_id in settings.admin_clerk_user_id_set
        return AuthUser(
            user_id=user_id,
            email=email,
            auth_mode=normalized_mode,
            is_admin=is_admin,
        )

    if auth_mode == AUTH_MODE_LEGACY:
        # Shared-password gate is in use (no per-user identity available).
        # Fall back to a single synthetic owner so the app remains functional.
        fallback = settings.dev_fallback_user_id or "shared-legacy-user"
        return AuthUser(
            user_id=f"legacy:{fallback}",
            email=None,
            auth_mode=AUTH_MODE_LEGACY,
            is_admin=True,
        )

    if not settings.enforce_per_user_identity:
        # Local development without Clerk configured; supply a deterministic
        # synthetic user so the existing workflow keeps working.
        fallback = settings.dev_fallback_user_id or "dev-local-user"
        return AuthUser(
            user_id=fallback,
            email=None,
            auth_mode="dev-fallback",
            is_admin=True,
        )

    return None


def get_current_user(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> AuthUser:
    user = resolve_current_user(request, settings)
    if user is None:
        raise UnauthorizedApiError(
            "Authentication is required to access this resource."
        )
    return user


def get_optional_current_user(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> Optional[AuthUser]:
    return resolve_current_user(request, settings)
