"""VoiceLoop: canonical audio in -> transcript -> agents -> spoken reply out.
Provider-blind; per-stage timings land in the same trace as agent events."""

from __future__ import annotations

import time
from dataclasses import dataclass

from bahi.config import Settings
from bahi.core.agent_loop import TraceEvent
from bahi.core.orchestrator import TurnEngine, TurnResult
from bahi.providers.base import AudioChunk, LanguageConfig, STTProvider, Synthesis, TTSProvider
from bahi.providers.factory import build_stt, build_tts


@dataclass
class VoiceTurnResult:
    transcript: str
    transcript_language: str | None
    turn: TurnResult
    reply_audio: AudioChunk
    stt_seconds: float
    tts_seconds: float
    total_seconds: float

    def to_dict(self) -> dict[str, object]:
        body = self.turn.to_dict()
        body["transcript"] = self.transcript
        body["transcript_language"] = self.transcript_language
        body["stt_seconds"] = round(self.stt_seconds, 3)
        body["tts_seconds"] = round(self.tts_seconds, 3)
        body["total_seconds"] = round(self.total_seconds, 3)
        return body


class VoiceLoop:
    def __init__(
        self,
        stt: STTProvider,
        tts: TTSProvider,
        engine: TurnEngine,
        language: LanguageConfig,
        reply_language: str,
        stt_provider_name: str = "",
        tts_provider_name: str = "",
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._engine = engine
        self._language = language
        self._reply_language = reply_language
        self._stt_name = stt_provider_name
        self._tts_name = tts_provider_name

    @classmethod
    def from_settings(cls, settings: Settings, engine: TurnEngine | None = None) -> VoiceLoop:
        return cls(
            stt=build_stt(settings),
            tts=build_tts(settings),
            engine=engine or TurnEngine.from_settings(settings),
            language=settings.language,
            reply_language=settings.reply_language,
            stt_provider_name=settings.stt_provider,
            tts_provider_name=settings.tts_provider,
        )

    def run(self, audio: AudioChunk) -> VoiceTurnResult:
        start = time.perf_counter()

        stt_start = time.perf_counter()
        transcript = self._stt.transcribe(audio, self._language)
        stt_seconds = time.perf_counter() - stt_start

        turn = self._engine.run_text_turn(transcript.text)

        tts_start = time.perf_counter()
        synthesis: Synthesis = self._tts.synthesize(turn.reply, self._reply_language)
        tts_seconds = time.perf_counter() - tts_start

        turn.events.insert(
            0,
            TraceEvent(
                kind="stt",
                label=f"stt:{self._stt_name}",
                seconds=stt_seconds,
                detail={
                    "transcript": transcript.text,
                    "language": transcript.language,
                    "audio_seconds": transcript.usage.audio_seconds,
                    "provider": self._stt_name,
                },
            ),
        )
        turn.events.append(
            TraceEvent(
                kind="tts",
                label=f"tts:{self._tts_name}",
                seconds=tts_seconds,
                detail={
                    "characters": synthesis.usage.characters,
                    "audio_seconds": synthesis.usage.audio_seconds,
                    "provider": self._tts_name,
                },
            ),
        )
        return VoiceTurnResult(
            transcript=transcript.text,
            transcript_language=transcript.language,
            turn=turn,
            reply_audio=synthesis.audio,
            stt_seconds=stt_seconds,
            tts_seconds=tts_seconds,
            total_seconds=time.perf_counter() - start,
        )
