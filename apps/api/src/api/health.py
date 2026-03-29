from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from src.api.dependencies import get_settings
from src.api.errors import response_envelope
from src.config.settings import AppSettings
from src.services.health_service import build_health_payload


router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
def health(request: Request, response: Response, settings: AppSettings = Depends(get_settings)):
    payload = build_health_payload(settings, request.app.state.session_factory)
    if payload.status == "failed":
        response.status_code = 503
    return response_envelope(request, payload.model_dump(mode="json"))

