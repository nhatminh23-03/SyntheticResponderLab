from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.errors import response_envelope
from src.services.model_catalog import list_interview_model_catalog


router = APIRouter(tags=["interview"])


@router.get("/api/v1/interview/models")
def interview_models_endpoint(request: Request):
    return response_envelope(request, list_interview_model_catalog())
