"""Deterministic Vision fake for tests (Vision itself is post-MVP stretch)."""

from __future__ import annotations

from typing import Any

from bahi.providers.base import VisionResult, VisionUsage


class FakeVision:
    name = "fake"

    def __init__(self, **_: Any) -> None:
        pass

    def extract(self, image: bytes, mime: str, instruction: str) -> VisionResult:
        return VisionResult(
            text="(fake extraction)",
            data={"items": []},
            usage=VisionUsage(pages=1),
        )
