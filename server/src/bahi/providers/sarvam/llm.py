from __future__ import annotations

import json
from typing import Any

import httpx

from bahi.providers.base import AssistantTurn, LLMUsage, Message, ToolCall, ToolSpec
from bahi.providers.sarvam import BASE_URL, raise_readable, require_key


def _to_wire(messages: list[Message]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": m.content}
            if m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in m.tool_calls
                ]
            wire.append(entry)
        elif m.role == "tool":
            wire.append(
                {"role": "tool", "content": m.content or "", "tool_call_id": m.tool_call_id}
            )
        else:
            wire.append({"role": m.role, "content": m.content or ""})
    return wire


class SarvamLLM:
    """Chat completions — OpenAI-compatible shape, verified live (Phase 0.5):
    native `tools`/`tool_choice` in, `message.tool_calls[]` out with
    `function.arguments` as a JSON string."""

    name = "sarvam"

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {require_key(api_key)}"},
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
            "messages": _to_wire(messages),
            "temperature": temperature,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"

        resp = self._client.post("/v1/chat/completions", json=body)
        raise_readable(resp, "chat")
        payload = resp.json()
        message = (payload.get("choices") or [{}])[0].get("message", {})

        tool_calls = tuple(
            ToolCall(
                id=tc.get("id", f"call_{i}"),
                name=tc["function"]["name"],
                arguments=_parse_arguments(tc["function"].get("arguments")),
            )
            for i, tc in enumerate(message.get("tool_calls") or [])
        )
        usage = payload.get("usage") or {}
        return AssistantTurn(
            content=message.get("content"),
            tool_calls=tool_calls,
            usage=LLMUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            ),
            model=payload.get("model", model),
            raw=payload,
        )


def _parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"_unparsed": raw or ""}
