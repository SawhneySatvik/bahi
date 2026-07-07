from __future__ import annotations

import json
from typing import Any

import httpx

from bahi.providers._http import post_with_retry
from bahi.providers.base import AssistantTurn, LLMUsage, Message, ToolCall, ToolSpec

BASE_URL = "https://generativelanguage.googleapis.com"


def _to_contents(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Translate the neutral transcript to Gemini's contents shape.
    system -> system_instruction; assistant -> role 'model' (text and/or
    functionCall parts); tool results -> user functionResponse keyed by NAME."""
    system_texts: list[str] = []
    contents: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            system_texts.append(m.content or "")
        elif m.role == "user":
            contents.append({"role": "user", "parts": [{"text": m.content or ""}]})
        elif m.role == "assistant":
            parts: list[dict[str, Any]] = []
            if m.content:
                parts.append({"text": m.content})
            parts.extend(
                {"functionCall": {"name": tc.name, "args": tc.arguments}}
                for tc in m.tool_calls
            )
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif m.role == "tool":
            try:
                response: Any = json.loads(m.content or "{}")
            except json.JSONDecodeError:
                response = {"result": m.content}
            if not isinstance(response, dict):
                response = {"result": response}
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": m.name or "tool", "response": response}}
                    ],
                }
            )
    return "\n\n".join(t for t in system_texts if t), contents


class GeminiLLM:
    name = "google"

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for provider 'google' — set it in .env")
        self._client = httpx.Client(
            base_url=BASE_URL, params={"key": api_key}, timeout=120, transport=transport
        )

    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        temperature: float = 0.0,
    ) -> AssistantTurn:
        system, contents = _to_contents(messages)
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in tools
                    ]
                }
            ]

        resp = post_with_retry(
            self._client, f"/v1beta/models/{model}:generateContent", json_body=body
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini chat failed ({resp.status_code}): {resp.text[:500]}")
        payload = resp.json()

        parts = (payload.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        texts = [p["text"] for p in parts if "text" in p]
        tool_calls = tuple(
            ToolCall(
                id=f"call_{i}_{p['functionCall']['name']}",
                name=p["functionCall"]["name"],
                arguments=p["functionCall"].get("args") or {},
            )
            for i, p in enumerate(parts)
            if "functionCall" in p
        )
        usage_meta = payload.get("usageMetadata") or {}
        return AssistantTurn(
            content="\n".join(texts) if texts else None,
            tool_calls=tool_calls,
            usage=LLMUsage(
                input_tokens=usage_meta.get("promptTokenCount", 0),
                # Gemini bills "thinking" tokens as output — count them (verified live)
                output_tokens=usage_meta.get("candidatesTokenCount", 0)
                + usage_meta.get("thoughtsTokenCount", 0),
                cached_input_tokens=usage_meta.get("cachedContentTokenCount", 0),
            ),
            model=payload.get("modelVersion", model),
            raw=payload,
        )
