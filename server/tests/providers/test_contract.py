"""Provider contract suite — every adapter must pass the SAME assertions.

Vendor adapters run against httpx.MockTransport loaded with the real recorded
responses from the Phase 0.5 spike (tests/fixtures/), so the wire shapes are
the ones the live APIs actually returned.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from bahi.providers.base import (
    AudioChunk,
    LanguageConfig,
    LLMProvider,
    Message,
    STTProvider,
    ToolCall,
    ToolSpec,
    TTSProvider,
)
from bahi.providers.elevenlabs.stt import ElevenLabsSTT
from bahi.providers.elevenlabs.tts import ElevenLabsTTS
from bahi.providers.fake.llm import FakeLLM
from bahi.providers.fake.stt import FakeSTT
from bahi.providers.fake.tts import FakeTTS, _silent_wav
from bahi.providers.google.llm import GeminiLLM
from bahi.providers.openai_.llm import OpenAILLM
from bahi.providers.sarvam.llm import SarvamLLM
from bahi.providers.sarvam.stt import SarvamSTT
from bahi.providers.sarvam.tts import SarvamTTS

FIXTURES = Path(__file__).parents[1] / "fixtures"

UDHAAR_TOOL = ToolSpec(
    name="add_udhaar",
    description="Record credit (udhaar) given to a customer",
    parameters={
        "type": "object",
        "properties": {
            "customer_name": {"type": "string"},
            "amount_paise": {"type": "integer"},
        },
        "required": ["customer_name", "amount_paise"],
    },
)

SARVAM_TEXT_RESPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "ठीक है, लिख दिया।"}}],
    "model": "sarvam-105b",
    "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
}

GEMINI_TEXT_RESPONSE = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": "ठीक है, लिख दिया।"}]}}],
    "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 8},
    "modelVersion": "gemini-2.5-flash",
}


def _fixture(rel: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / rel).read_text())
    return data


def sarvam_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/speech-to-text":
            stt_fx = _fixture("sarvam/stt_saaras_v3_codemix.json")["response"]
            return httpx.Response(200, json=stt_fx)
        if path == "/text-to-speech":
            audio_b64 = base64.b64encode(_silent_wav()).decode()
            return httpx.Response(200, json={"audios": [audio_b64], "request_id": "fx"})
        if path == "/v1/chat/completions":
            body = json.loads(request.content)
            if body.get("tools"):
                chat_fx = _fixture("sarvam/chat_105b_tool_call.json")["response"]
                return httpx.Response(200, json=chat_fx)
            return httpx.Response(200, json=SARVAM_TEXT_RESPONSE)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


OPENAI_TOOL_RESPONSE = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_ab12",
                        "type": "function",
                        "function": {
                            "name": "add_udhaar",
                            "arguments": '{"customer_name": "Ramesh", "amount_paise": 20000}',
                        },
                    }
                ],
            }
        }
    ],
    "model": "gpt-5.4-mini-2026-03-17",
    "usage": {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "prompt_tokens_details": {"cached_tokens": 0},
    },
}

OPENAI_TEXT_RESPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "theek hai, likh diya."}}],
    "model": "gpt-5.4-mini-2026-03-17",
    "usage": {"prompt_tokens": 20, "completion_tokens": 8},
}


def openai_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "reasoning" not in body  # 5.4 rejects tools with reasoning:none
        assert "temperature" not in body  # fixed on gpt-5* models
        if body.get("tools"):
            return httpx.Response(200, json=OPENAI_TOOL_RESPONSE)
        return httpx.Response(200, json=OPENAI_TEXT_RESPONSE)

    return httpx.MockTransport(handler)


def elevenlabs_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/speech-to-text":
            return httpx.Response(
                200,
                json={
                    "language_code": "hi",
                    "language_probability": 0.97,
                    "text": "रमेश को दो सौ रुपये उधार लिख दो",
                    "words": [],
                },
            )
        if path.startswith("/v1/text-to-speech/"):
            return httpx.Response(
                200, content=b"\xff\xfb" + b"\x00" * 512, headers={"request-id": "fx"}
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def gemini_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("tools"):
            return httpx.Response(
                200, json=_fixture("google/gemini_25_flash_function_call.json")["response"]
            )
        return httpx.Response(200, json=GEMINI_TEXT_RESPONSE)

    return httpx.MockTransport(handler)


# --- LLM contract ---


def _fake_llm_with_tool_call() -> tuple[LLMProvider, str]:
    llm = FakeLLM()
    llm.enqueue_tool_call("add_udhaar", {"customer_name": "Ramesh", "amount_paise": 20000})
    return llm, "fake-model"


LLM_CASES: dict[str, Callable[[], tuple[LLMProvider, str]]] = {
    "fake": _fake_llm_with_tool_call,
    "sarvam": lambda: (SarvamLLM(api_key="test", transport=sarvam_transport()), "sarvam-105b"),
    "google": lambda: (GeminiLLM(api_key="test", transport=gemini_transport()), "gemini-2.5-flash"),
    "openai": lambda: (OpenAILLM(api_key="test", transport=openai_transport()), "gpt-5.4-mini"),
}


@pytest.fixture(params=sorted(LLM_CASES))
def llm_case(request: pytest.FixtureRequest) -> tuple[LLMProvider, str]:
    return LLM_CASES[request.param]()


def _messages() -> list[Message]:
    return [
        Message(role="system", content="You manage a shop ledger. Use tools."),
        Message(role="user", content="Ramesh ko 200 rupaye udhaar likh do"),
    ]


def test_llm_tool_call_contract(llm_case: tuple[LLMProvider, str]) -> None:
    llm, model = llm_case
    turn = llm.complete(_messages(), [UDHAAR_TOOL], model=model, temperature=0.0)
    assert turn.tool_calls, "expected a tool call for an udhaar utterance"
    call = turn.tool_calls[0]
    assert call.name == "add_udhaar"
    assert isinstance(call.arguments, dict)
    assert call.arguments["customer_name"] == "Ramesh"
    assert isinstance(call.arguments["amount_paise"], int)
    assert call.id
    assert turn.usage.kind == "llm"


def test_llm_text_contract(llm_case: tuple[LLMProvider, str]) -> None:
    llm, model = llm_case
    if isinstance(llm, FakeLLM):
        llm = FakeLLM()  # fresh queue: this test wants a text turn, not the scripted tool call
        llm.enqueue_text("theek hai")
    turn = llm.complete(_messages(), [], model=model, temperature=0.0)
    assert turn.content
    assert not turn.tool_calls
    assert turn.usage.kind == "llm"
    assert turn.usage.output_tokens >= 0


def test_llm_multi_hop_transcript_roundtrip(llm_case: tuple[LLMProvider, str]) -> None:
    """The full tool loop transcript (assistant tool_call -> tool result) must
    be translatable by every adapter without error."""
    llm, model = llm_case
    if isinstance(llm, FakeLLM):
        llm = FakeLLM()
        llm.enqueue_text("done")
    first_call = Message(
        role="assistant",
        tool_calls=(
            ToolCall(
                id="call_0",
                name="add_udhaar",
                arguments={"customer_name": "Ramesh", "amount_paise": 20000},
            ),
        ),
    )
    transcript = [
        *_messages(),
        first_call,
        Message(
            role="tool",
            content=json.dumps({"new_balance_paise": 20000}),
            tool_call_id="call_0",
            name="add_udhaar",
        ),
    ]
    turn = llm.complete(transcript, [UDHAAR_TOOL], model=model, temperature=0.0)
    assert turn.usage.kind == "llm"


# --- STT contract ---

STT_CASES: dict[str, Callable[[], STTProvider]] = {
    "fake": FakeSTT,
    "sarvam": lambda: SarvamSTT(api_key="test", transport=sarvam_transport()),
    "elevenlabs": lambda: ElevenLabsSTT(api_key="test", transport=elevenlabs_transport()),
}


@pytest.fixture(params=sorted(STT_CASES))
def stt(request: pytest.FixtureRequest) -> STTProvider:
    return STT_CASES[request.param]()


def test_stt_contract(stt: STTProvider) -> None:
    audio = AudioChunk(data=_silent_wav(), mime="audio/wav", sample_rate=16000, channels=1)
    transcript = stt.transcribe(audio, LanguageConfig(hints=("hi", "en"), codemix=True))
    assert transcript.text
    assert transcript.usage.kind == "stt"
    assert transcript.usage.audio_seconds >= 0


# --- TTS contract ---

TTS_CASES: dict[str, Callable[[], TTSProvider]] = {
    "fake": FakeTTS,
    "sarvam": lambda: SarvamTTS(api_key="test", transport=sarvam_transport()),
    "elevenlabs": lambda: ElevenLabsTTS(api_key="test", transport=elevenlabs_transport()),
}


@pytest.fixture(params=sorted(TTS_CASES))
def tts(request: pytest.FixtureRequest) -> TTSProvider:
    return TTS_CASES[request.param]()


def test_tts_contract(tts: TTSProvider) -> None:
    text = "Ramesh ka balance do sau rupaye hai"
    synthesis = tts.synthesize(text, "hi")
    assert synthesis.audio.data
    assert synthesis.audio.mime.startswith("audio/")
    assert synthesis.usage.kind == "tts"
    assert synthesis.usage.characters == len(text)


# --- key hygiene ---


def test_vendor_adapters_demand_keys_with_actionable_errors() -> None:
    with pytest.raises(ValueError, match="SARVAM_API_KEY"):
        SarvamLLM(api_key=None)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GeminiLLM(api_key=None)
    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        ElevenLabsSTT(api_key=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAILLM(api_key=None)
