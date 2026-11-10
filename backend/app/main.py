"""FastAPI entry point for the local AirScan backend."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings, get_settings


class HealthResponse(BaseModel):
    """Minimal response used to verify that the backend is available."""

    status: str
    service: str
    host: str
    port: int


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the local AirScan API application."""

    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="AirScan Local Backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.settings = resolved_settings

    @application.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Return backend availability and non-sensitive local configuration."""

        return HealthResponse(
            status="ok",
            service="airscan-backend",
            host=resolved_settings.host,
            port=resolved_settings.port,
        )

    return application


app = create_app()