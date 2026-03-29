from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    status: str
    message: Optional[str] = None
    details: dict = Field(default_factory=dict)


class HealthPayload(BaseModel):
    status: str
    checks: dict[str, HealthCheckResult]
