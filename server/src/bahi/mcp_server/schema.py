"""Derive a ToolSpec JSON schema from a plain function signature, so tool
behavior, in-process spec, and MCP registration all share ONE definition."""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from typing import Any

_PRIMITIVES: dict[type, dict[str, Any]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
}


def _json_type(annotation: Any) -> dict[str, Any]:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _json_type(non_none[0]) if len(non_none) == 1 else {}
    if origin in (list, typing.List):  # noqa: UP006
        args = typing.get_args(annotation)
        return {"type": "array", "items": _json_type(args[0]) if args else {}}
    if origin in (dict, typing.Dict) or annotation is dict:  # noqa: UP006
        return {"type": "object"}
    return _PRIMITIVES.get(annotation, {})


def schema_from_signature(fn: Callable[..., Any]) -> dict[str, Any]:
    hints = typing.get_type_hints(fn)
    signature = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in signature.parameters.items():
        if name in ("self", "return"):
            continue
        properties[name] = _json_type(hints.get(name, str))
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}
