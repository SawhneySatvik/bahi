"""FastAPI application. Endpoints grow by phase; /health ships in Phase 0
and reports the resolved provider profile (the config-not-code proof)."""

from __future__ import annotations

from fastapi import FastAPI

from bahi import __version__
from bahi.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Bahi", version=__version__)

    @app.get("/health")
    def health() -> dict[str, object]:
        settings = get_settings()
        return {"status": "ok", "version": __version__, "profile": settings.profile_summary()}

    return app


app = create_app()
