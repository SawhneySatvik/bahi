"""Provider registry: name → adapter, resolved lazily so a missing vendor
SDK only fails when that vendor is actually selected by config.

Registration is declarative (module path strings), so importing the registry
never imports any vendor SDK. Adding a provider = one entry per capability
here + an adapter package; core code never changes.
"""

from __future__ import annotations

import importlib
from typing import Any

Capability = str  # "stt" | "tts" | "llm" | "vision"

# capability -> provider name -> "module:ClassName"
_REGISTRY: dict[Capability, dict[str, str]] = {
    "stt": {
        "fake": "bahi.providers.fake.stt:FakeSTT",
    },
    "tts": {
        "fake": "bahi.providers.fake.tts:FakeTTS",
    },
    "llm": {
        "fake": "bahi.providers.fake.llm:FakeLLM",
    },
    "vision": {
        "fake": "bahi.providers.fake.vision:FakeVision",
    },
}


class UnknownProviderError(LookupError):
    def __init__(self, capability: Capability, name: str) -> None:
        available = ", ".join(sorted(_REGISTRY.get(capability, {}))) or "(none)"
        super().__init__(
            f"No {capability!r} provider named {name!r}. Available: {available}. "
            f"Set BAHI_{capability.upper()}_PROVIDER (or the per-role LLM vars) "
            f"to one of these, or register the provider in bahi.providers.registry."
        )
        self.capability = capability
        self.name = name


def register(capability: Capability, name: str, target: str) -> None:
    """Register an adapter as 'module:ClassName' (used by tests/plugins)."""
    _REGISTRY.setdefault(capability, {})[name] = target


def available(capability: Capability) -> list[str]:
    return sorted(_REGISTRY.get(capability, {}))


def create(capability: Capability, name: str, **kwargs: Any) -> Any:
    """Instantiate the adapter for (capability, name).

    kwargs are passed to the adapter constructor (e.g. api_key, voice_ref
    defaults) by the composition root; adapters validate their own needs.
    """
    try:
        target = _REGISTRY[capability][name]
    except KeyError:
        raise UnknownProviderError(capability, name) from None
    module_name, _, class_name = target.partition(":")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls(**kwargs)
