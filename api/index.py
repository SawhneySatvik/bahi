"""Vercel entrypoint: Bahi's Alexa+ ledger MCP server as one Python (ASGI) function.

`vercel.json` rewrites every path here, passing the original path as `?__path=`.
`/mcp` is the Streamable HTTP endpoint (MCP spec 2025-11-25, stateless, JSON
responses); `/` serves the simulated Echo Show.

Serverless has no reliable ASGI lifespan, so instead of the long-lived session
manager FastMCP wires into its lifespan, each `/mcp` request gets a fresh
stateless session manager, which is all stateless Streamable HTTP needs.

Storage is SQLite in /tmp (the only writable path): per instance and ephemeral.
Every cold start seeds the demo kirana day so the ledger is never empty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/bahi.db")
os.environ.setdefault("BAHI_TZ", "America/Los_Angeles")

_SERVER = Path(__file__).resolve().parent.parent / "server"
sys.path[:0] = [str(_SERVER / "src"), str(_SERVER / "scripts")]

from bahi.mcp_server.http import build_http_server  # noqa: E402
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager  # noqa: E402
from seed_demo import main as seed_demo  # noqa: E402

seed_demo()  # init_db() + demo rows; no-op when the ledger already has entries

_mcp = build_http_server("0.0.0.0", 8765)
_site = _mcp.streamable_http_app()  # serves GET / (Echo Show page)


def _original_path(scope: dict[str, Any]) -> dict[str, Any]:
    """The rewrite in vercel.json hands the function `/api/index?__path=<original>`;
    restore the original path so Starlette and the /mcp check route correctly."""
    query = parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True)
    path = next((v for k, v in query if k == "__path"), None)
    if path is None:
        return scope
    path = "/" + path.lstrip("/")
    rest = urlencode([(k, v) for k, v in query if k != "__path"]).encode()
    return {**scope, "path": path, "raw_path": path.encode(), "query_string": rest}


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] == "http":
        scope = _original_path(scope)
    if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
        manager = StreamableHTTPSessionManager(
            app=_mcp._mcp_server,
            json_response=_mcp.settings.json_response,
            stateless=True,
            security_settings=_mcp.settings.transport_security,
        )
        async with manager.run():
            await manager.handle_request(scope, receive, send)
        return
    await _site(scope, receive, send)
