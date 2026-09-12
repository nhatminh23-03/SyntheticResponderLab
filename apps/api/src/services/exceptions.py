from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.services.interview_cache import InterviewAnswer


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


class ProviderRunInFlightApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(409, "provider_run_in_flight", message, details)


class UnauthorizedApiError(ApiError):
    def __init__(self, message: str = "Authentication is required.", details: Optional[dict] = None) -> None:
        super().__init__(401, "unauthorized", message, details)


class ForbiddenApiError(ApiError):
    def __init__(self, message: str = "You do not have access to this resource.", details: Optional[dict] = None) -> None:
        super().__init__(403, "forbidden", message, details)


class UnsupportedMediaTypeApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(415, "unsupported_media_type", message, details)


class PayloadTooLargeApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(413, "payload_too_large", message, details)

class QuotaExceededApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(429, "quota_exceeded", message, details)


class ProviderUnavailableApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(503, "provider_unavailable", message, details)


class DependencyMissingApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(503, "dependency_missing", message, details)


class LegacyModuleApiError(ApiError):
    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(500, "legacy_module_error", message, details)


class TransientProviderError(RuntimeError):
    """The provider answered, but the answer was unusable.

    Empty completion text, a missing message, or a body that is not JSON. These
    are hiccups a retry usually clears, and they are distinct from a
    misconfiguration (no API key) or a budget stop, both of which must stay
    fatal. Only raise this where the fault is demonstrably the response itself.
    """

    def __init__(self, message: str, *, measured_usage: InterviewAnswer | None = None) -> None:
        super().__init__(message)
        self.measured_usage = measured_usage
