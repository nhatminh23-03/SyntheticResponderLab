from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.dependencies import get_db_session
from src.api.errors import response_envelope
from src.services.persona_service import list_personas


router = APIRouter(tags=["personas"])


@router.get("/api/v1/personas")
def personas_endpoint(
    request: Request,
    db: Session = Depends(get_db_session),
):
    return response_envelope(
        request,
        {
            "personas": list_personas(db),
            "source": "database",
        },
    )
