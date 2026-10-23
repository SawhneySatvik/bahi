"""End-to-end check of the Alexa+ MCP endpoint over Streamable HTTP.

initialize (asserts negotiated protocolVersion == 2025-11-25) → tools/list → tools/call.

Usage: .venv/bin/python scripts/mcp_http_check.py [URL]   (default http://127.0.0.1:8765/mcp)
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

EXPECTED_PROTOCOL = "2025-11-25"


async def main(url: str) -> None:
    async with (
        streamablehttp_client(url) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        print(f"server: {init.serverInfo.name}  protocolVersion: {init.protocolVersion}")
        assert init.protocolVersion == EXPECTED_PROTOCOL, init.protocolVersion

        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        print("tools:", ", ".join(names))
        assert {"shop_brief", "add_udhaar", "list_debtors"} <= set(names)

        brief = await session.call_tool("shop_brief", {})
        print(
            "shop_brief →",
            json.dumps(
                brief.structuredContent or brief.content[0].model_dump(), ensure_ascii=False
            )[:600],
        )
        assert not brief.isError
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mcp"))
