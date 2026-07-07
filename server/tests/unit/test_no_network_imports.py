"""The sovereign guarantee, enforced: importing the ledger must not pull in
any network stack or any vendor adapter. Runs in a subprocess so this test's
own imports don't bleed.

`bahi.providers.base` is explicitly allowed — it is pure dataclasses/Protocols
(the contract types config reuses, e.g. LanguageConfig) with zero I/O. What
must never appear are HTTP stacks and vendor adapter packages.
"""

from __future__ import annotations

import subprocess
import sys

BLOCKLIST = [
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "websockets",
    "bahi.providers.sarvam",
    "bahi.providers.elevenlabs",
    "bahi.providers.google",
    "bahi.providers.openai_",
]

PROBE = f"""
import sys
import bahi.ledger.models
import bahi.ledger.repository
import bahi.ledger.db
leaked = [m for m in {BLOCKLIST!r} if m in sys.modules]
sys.exit(0 if not leaked else print(f"network modules leaked into ledger: {{leaked}}") or 1)
"""


def test_ledger_has_zero_network_imports() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
