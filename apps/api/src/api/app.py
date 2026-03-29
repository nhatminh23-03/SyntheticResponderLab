from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import install_exception_handlers
from src.api.health import router as health_router
from src.api.studies import router as studies_router
from src.config.settings import AppSettings, get_settings
from src.persistence.session import create_session_factory, get_session_factory
from src.services.health_service import startup_failures


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    session_factory = create_session_factory(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        failures = startup_failures(resolved_settings, session_factory)
        if failures:
            raise RuntimeError(f"Startup checks failed: {', '.join(failures)}")
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
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(studies_router)
    return app
