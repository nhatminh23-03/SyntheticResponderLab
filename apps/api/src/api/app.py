from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.errors import install_exception_handlers
from src.api.errors import build_meta_error, new_request_id
from src.api.health import router as health_router
from src.api.studies import router as studies_router
from src.config.settings import AppSettings, get_settings
from src.persistence.session import create_session_factory, get_session_factory
from src.services.health_service import build_health_payload, startup_failures


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    session_factory = create_session_factory(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        failures = startup_failures(resolved_settings, session_factory)
        if failures:
            health_payload = build_health_payload(resolved_settings, session_factory)
            failure_messages = []
            for name in failures:
                check = health_payload.checks.get(name)
                if check is None:
                    failure_messages.append(name)
                    continue
                detail = f"{name}: {check.message or 'failed'}"
                failure_messages.append(detail)
            raise RuntimeError(f"Startup checks failed: {'; '.join(failure_messages)}")
        yield

    app = FastAPI(title="Synthetic Responder API", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allow_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_deployment_secret(request, call_next):
        protected_prefix = "/api/v1/"
        if (
            request.url.path.startswith(protected_prefix)
            and request.url.path != "/api/v1/health"
            and resolved_settings.deployment_shared_secret
        ):
            provided = request.headers.get("X-Deployment-Secret")
            if provided != resolved_settings.deployment_shared_secret:
                request_id = new_request_id()
                return JSONResponse(
                    status_code=401,
                    content=build_meta_error(
                        request_id,
                        "unauthorized",
                        "Request is missing a valid deployment access token.",
                    ),
                    headers={"X-Request-ID": request_id},
                )
        return await call_next(request)

    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(studies_router)
    return app
