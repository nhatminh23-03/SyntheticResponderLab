from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MetaEnvelope(BaseModel):
    request_id: str
    generated_at: datetime


class ApiResponse(BaseModel):
    data: dict[str, Any]
    meta: MetaEnvelope


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorPayload

