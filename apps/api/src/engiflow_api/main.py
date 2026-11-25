"""Fábrica da aplicação FastAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from engiflow_api.core.config import Settings, get_settings
from engiflow_api.infrastructure.db import build_engine, build_session_factory
from engiflow_api.presentation.errors import install_error_handlers
from engiflow_api.presentation.middleware import configure_logging, correlation_middleware
from engiflow_api.presentation.routes.datasets import router as datasets_router
from engiflow_api.presentation.routes.operations import router as operations_router
from engiflow_api.presentation.routes.system import router as system_router
from engiflow_api.presentation.routes.templates import router as templates_router


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(
        title="EngiFlow API",
        version=cfg.app_version,
        description="API do EngiFlow (uso individual, local).",
    )
    app.state.session_factory = session_factory or build_session_factory(
        build_engine(cfg.database_url)
    )

    app.middleware("http")(correlation_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-Id", "Idempotency-Key"],
        expose_headers=["X-Correlation-Id"],
    )
    install_error_handlers(app)
    app.include_router(system_router)
    app.include_router(datasets_router)
    app.include_router(operations_router)
    app.include_router(templates_router)
    return app


def get_app() -> FastAPI:
    """Ponto de entrada: `uvicorn engiflow_api.main:get_app --factory`."""
    return create_app()
