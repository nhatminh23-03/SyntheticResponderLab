"""TypeSafe Jev engine: the error classes live here so run routing can import them; the engine itself comes in Task 5."""
from src.services.exceptions import ProviderUnavailableApiError


class JevUnavailableError(ProviderUnavailableApiError):
    """Jev answered no respondent (network, timeouts, 5xx): the run falls back to the preloaded demo."""


class JevRequestError(ProviderUnavailableApiError):
    """Jev refused the request (bad key, bad payload): the run stops with this message."""


class JevTooManyFailuresError(ProviderUnavailableApiError):
    """More than MAX_FAILED_SHARE of respondents failed: the run fails visibly so the instructor can retry."""


MAX_FAILED_SHARE = 0.20
