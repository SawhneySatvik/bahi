from __future__ import annotations

from typing import Any

import httpx

from bahi.providers._http import post_with_retry
from bahi.providers._openai_wire import messages_to_wire, parse_completion, tools_to_wire
from bahi.providers.base import AssistantTurn, Message, ToolSpec

BASE_URL = "https://api.openai.com"


class OpenAILLM:
    """Chat Completions (still supported; thinner adapter surface than the
    Responses API). Verified 2026-07-08: small tier = gpt-5.4-mini/nano;
    5.4 models reject tool calling with reasoning:none — we never send a
    reasoning param, and temperature is omitted for gpt-5* (fixed by API)."""

    name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for provider 'openai' — set it in .env")
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=120,
            transport=transport,
        )

    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        temperature: float = 0.0,
    ) -> AssistantTurn:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages_to_wire(messages),
        }
        if not model.startswith(("gpt-5", "o")):
            body["temperature"] = temperature
        if tools:
            body["tools"] = tools_to_wire(tools)
            body["tool_choice"] = "auto"

        resp = post_with_retry(self._client, "/v1/chat/completions", json_body=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenAI chat failed ({resp.status_code}): {resp.text[:500]}")
        return parse_completion(resp.json(), model)
