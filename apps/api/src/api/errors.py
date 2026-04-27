from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.schemas.common import ErrorResponse, ErrorPayload
from src.services.exceptions import ApiError


def new_request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def build_meta_error(request_id: str, code: str, message: str, details: Optional[dict] = None) -> dict:
    payload = ErrorResponse(
        error=ErrorPayload(
            code=code,
            message=message,
            details=details or {},
            request_id=request_id,
        )
    )
    return payload.model_dump(mode="json")


def install_exception_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = new_request_id()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        request_id = getattr(request.state, "request_id", new_request_id())
        return JSONResponse(
            status_code=exc.status_code,
            content=build_meta_error(request_id, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", new_request_id())
        return JSONResponse(
            status_code=400,
            content=build_meta_error(
                request_id,
                "validation_error",
                "Request validation failed.",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", new_request_id())
        settings = getattr(request.app.state, "settings", None)
        is_debug = bool(getattr(settings, "app_debug", False))
        message = f"Unexpected server error: {exc}" if is_debug else "Unexpected server error."
        return JSONResponse(
            status_code=500,
            content=build_meta_error(request_id, "legacy_module_error", message, {}),
        )


def response_envelope(request: Request, data: dict) -> dict:
    request_id = getattr(request.state, "request_id", new_request_id())
    return {
        "data": data,
        "meta": {
            "request_id": request_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
