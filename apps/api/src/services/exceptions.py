from __future__ import annotations

from typing import Optional


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class ValidationApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(400, "validation_error", message, details)


class NotFoundApiError(ApiError):
    def __init__(self, message: str = "Resource not found.", details: Optional[dict] = None) -> None:
        super().__init__(404, "not_found", message, details)


class ConflictApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(409, "conflict", message, details)


class UnsupportedMediaTypeApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(415, "unsupported_media_type", message, details)


class ProviderUnavailableApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(503, "provider_unavailable", message, details)


class DependencyMissingApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(503, "dependency_missing", message, details)


class LegacyModuleApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(500, "legacy_module_error", message, details)
