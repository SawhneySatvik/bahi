"""FastAPI application. /health (Phase 0), /api/turn text (Phase 3),
/api/turn/audio — the full voice loop (Phase 5)."""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from bahi import __version__
from bahi.api.audio import TranscodeError, to_canonical_wav
from bahi.config import get_settings
from bahi.core.orchestrator import TurnEngine
from bahi.core.voice import VoiceLoop
from bahi.ledger.db import init_db

MAX_AUDIO_BYTES = 4_000_000  # stay under serverless body caps; ~2 min of opus


class TurnRequest(BaseModel):
    text: str


@lru_cache(maxsize=1)
def get_engine() -> TurnEngine:
    return TurnEngine.from_settings(get_settings())


@lru_cache(maxsize=1)
def get_voice_loop() -> VoiceLoop:
    return VoiceLoop.from_settings(get_settings(), engine=get_engine())


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

    @app.get("/api/ledger")
    def ledger() -> dict[str, Any]:
        from bahi.ledger.db import session_scope
        from bahi.ledger.repository import LedgerRepository, rupees

        with session_scope() as session:
            repo = LedgerRepository(session, tz=get_settings().tz)
            customers = repo.list_customers_with_balances()
            recent = repo.recent_transactions(20)
            today = repo.day_summary()
            return {
                "customers": [
                    {"name": c.name, "balance_paise": b, "balance": rupees(b)}
                    for c, b in customers
                ],
                "transactions": [
                    {
                        "id": t.id,
                        "type": t.type,
                        "amount_paise": t.amount_paise,
                        "amount": rupees(t.amount_paise),
                        "customer": t.customer.name if t.customer else None,
                        "ts": t.ts.isoformat(timespec="seconds"),
                    }
                    for t in recent
                ],
                "today": {
                    "date": today["date"],
                    "sales": rupees(today["sales_paise"]),
                    "udhaar_given": rupees(today["udhaar_given_paise"]),
                    "repayments_received": rupees(today["repayments_received_paise"]),
                    "cash_in": rupees(today["cash_in_paise"]),
                },
            }

    @app.post("/api/turn/audio")
    async def turn_audio(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        raw = await file.read()
        if len(raw) > MAX_AUDIO_BYTES:
            raise HTTPException(413, f"audio too large (>{MAX_AUDIO_BYTES} bytes)")
        try:
            audio = to_canonical_wav(raw, file.content_type or "application/octet-stream")
        except TranscodeError as exc:
            raise HTTPException(422, str(exc)) from exc
        result = get_voice_loop().run(audio)
        body = result.to_dict()
        body["reply_audio_b64"] = base64.b64encode(result.reply_audio.data).decode()
        body["reply_audio_mime"] = result.reply_audio.mime
        return body

    return app


app = create_app()
