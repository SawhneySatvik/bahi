"""The ledger as a real MCP server — same tool functions the agent loop uses,
served over stdio for Claude Code / Claude Desktop / any MCP client, or over
Streamable HTTP for Alexa+ (see `bahi.mcp_server.http`)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from bahi.ledger.db import init_db
from bahi.mcp_server.tools import LEDGER_TOOL_FUNCTIONS


def build_server(**settings: Any) -> FastMCP:
    server = FastMCP(
        "bahi-ledger",
        instructions=(
            "Shop ledger (bahi-khata) for a kirana store. Money is integer paise "
            "(₹1 = 100 paise). Record sales, udhaar (credit), repayments; query "
            "balances, debtors, and day summaries."
        ),
        **settings,
    )
    for fn in LEDGER_TOOL_FUNCTIONS:
        server.add_tool(fn)
    return server


def main() -> None:
    init_db()
    build_server().run()


if __name__ == "__main__":
    main()
