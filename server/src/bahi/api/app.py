"""FastAPI application. /health ships since Phase 0; /api/turn (text) since
Phase 3 — the audio path arrives with the voice loop (Phase 5)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from bahi import __version__
from bahi.config import get_settings
from bahi.core.orchestrator import TurnEngine
from bahi.ledger.db import init_db


class TurnRequest(BaseModel):
    text: str


@lru_cache(maxsize=1)
def get_engine() -> TurnEngine:
    return TurnEngine.from_settings(get_settings())


def create_app() -> FastAPI:
    app = FastAPI(title="Bahi", version=__version__)

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    @app.get("/health")
    def health() -> dict[str, object]:
        settings = get_settings()
        return {"status": "ok", "version": __version__, "profile": settings.profile_summary()}

    @app.post("/api/turn")
    def turn(body: TurnRequest) -> dict[str, Any]:
        return get_engine().run_text_turn(body.text).to_dict()

    return app


app = create_app()
