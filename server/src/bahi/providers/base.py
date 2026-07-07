"""Provider contracts — the plug-and-play boundary.

Every external model capability (STT, TTS, LLM chat + tool-calling, Vision)
is consumed by the core exclusively through the Protocols in this module.
Adapters translate these shapes to their vendor SDK/API; no vendor SDK import
may appear outside its adapter package.

Semantics that adapters MUST honor:
- All text is UTF-8 Python str; languages are BCP-47-ish lowercase codes
  ("hi", "en"). `LanguageConfig.codemix=True` means the user freely mixes the
  hint languages in one utterance; adapters map this to the closest vendor
  concept (e.g. Saaras `mode=codemix`, Scribe auto-detect) and never expose
  the vendor term.
- Money never flows through providers; providers see only utterance text and
  tool results the LLM explicitly requested (data-boundary contract).
- Usage is reported in the unit the vendor actually bills (tagged union
  below) so cost accounting never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Shared value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageConfig:
    """Core-neutral language selection (never a vendor mode name)."""

    hints: tuple[str, ...] = ("hi", "en")
    codemix: bool = True


@dataclass(frozen=True)
class AudioChunk:
    """Audio bytes plus enough metadata to play or transcode them.

    `mime` examples: "audio/wav", "audio/webm;codecs=opus", "audio/mpeg".
    `sample_rate`/`channels` may be None when the container self-describes.
    """

    data: bytes
    mime: str
    sample_rate: int | None = None
    channels: int | None = None


# --- Usage: tagged per-capability union (vendors bill in different units) ---


@dataclass(frozen=True)
class LLMUsage:
    kind: Literal["llm"] = "llm"
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class STTUsage:
    kind: Literal["stt"] = "stt"
    audio_seconds: float = 0.0


@dataclass(frozen=True)
class TTSUsage:
    kind: Literal["tts"] = "tts"
    characters: int = 0
    audio_seconds: float = 0.0


@dataclass(frozen=True)
class VisionUsage:
    kind: Literal["vision"] = "vision"
    pages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


Usage = LLMUsage | STTUsage | TTSUsage | VisionUsage


# --- STT / TTS results ---


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    usage: STTUsage
    raw: Any = None  # vendor response for debugging; never read by core


@dataclass(frozen=True)
class Synthesis:
    audio: AudioChunk
    usage: TTSUsage
    raw: Any = None


# --- LLM chat + tool-calling ---


@dataclass(frozen=True)
class ToolSpec:
    """A callable tool advertised to the LLM. `parameters` is JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    """One turn in the provider-neutral conversation transcript.

    role="tool" messages carry the result of a ToolCall in `content` and
    must set `tool_call_id`. Assistant messages may carry `tool_calls`.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    tool_call_id: str | None = None
    name: str | None = None  # tool name on role="tool" (Gemini keys results by name)


@dataclass(frozen=True)
class AssistantTurn:
    """What an LLMProvider returns: text, tool calls, or both."""

    content: str | None
    tool_calls: tuple[ToolCall, ...]
    usage: LLMUsage
    model: str
    raw: Any = None

    @property
    def message(self) -> Message:
        return Message(role="assistant", content=self.content, tool_calls=self.tool_calls)


# --- Vision ---


@dataclass(frozen=True)
class VisionResult:
    """Structured extraction from an image/document."""

    text: str
    data: dict[str, Any] | None
    usage: VisionUsage
    raw: Any = None


# ---------------------------------------------------------------------------
# Provider Protocols (the contracts adapters implement)
# ---------------------------------------------------------------------------


@runtime_checkable
class STTProvider(Protocol):
    name: str

    def transcribe(self, audio: AudioChunk, language: LanguageConfig) -> Transcript:
        """Transcribe one utterance. `audio` is canonical 16kHz mono PCM WAV
        unless the adapter declares it accepts the original container."""
        ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, language: str, voice_ref: str | None = None) -> Synthesis:
        """Speak `text` in `language`. `voice_ref` is an opaque profile-env
        value (Bulbul speaker / ElevenLabs voice id); core never sets it."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        temperature: float = 0.0,
    ) -> AssistantTurn:
        """One chat completion with optional tool-calling. Adapters for
        vendors without native tool-calling implement the same contract via
        constrained JSON prompting — the caller cannot tell the difference."""
        ...


@runtime_checkable
class VisionProvider(Protocol):
    name: str

    def extract(self, image: bytes, mime: str, instruction: str) -> VisionResult:
        """Extract text/structure from an image or document page."""
        ...
