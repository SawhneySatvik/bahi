"""Shared translation for OpenAI-compatible chat APIs (OpenAI itself, and
Sarvam, whose chat endpoint speaks the same shape — verified live Phase 0.5)."""

from __future__ import annotations

import json
from typing import Any

from bahi.providers.base import AssistantTurn, LLMUsage, Message, ToolCall, ToolSpec


def messages_to_wire(messages: list[Message]) -> list[dict[str, Any]]:
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


def tools_to_wire(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
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


def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"_unparsed": raw or ""}


def parse_completion(payload: dict[str, Any], requested_model: str) -> AssistantTurn:
    message = (payload.get("choices") or [{}])[0].get("message", {})
    tool_calls = tuple(
        ToolCall(
            id=tc.get("id", f"call_{i}"),
            name=tc["function"]["name"],
            arguments=parse_arguments(tc["function"].get("arguments")),
        )
        for i, tc in enumerate(message.get("tool_calls") or [])
    )
    usage = payload.get("usage") or {}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    return AssistantTurn(
        content=message.get("content"),
        tool_calls=tool_calls,
        usage=LLMUsage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cached_input_tokens=cached or 0,
        ),
        model=payload.get("model", requested_model),
        raw=payload,
    )
