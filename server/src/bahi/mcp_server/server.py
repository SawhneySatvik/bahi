"""The ledger as a real MCP server — same tool functions the agent loop uses,
served over stdio for Claude Code / Claude Desktop / any MCP client."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from bahi.ledger.db import init_db
from bahi.mcp_server.tools import LEDGER_TOOL_FUNCTIONS


def build_server() -> FastMCP:
    server = FastMCP(
        "bahi-ledger",
        instructions=(
            "Shop ledger (bahi-khata) for a kirana store. Money is integer paise "
            "(₹1 = 100 paise). Record sales, udhaar (credit), repayments; query "
            "balances, debtors, and day summaries."
        ),
    )
    for fn in LEDGER_TOOL_FUNCTIONS:
        server.add_tool(fn)
    return server


def main() -> None:
    init_db()
    build_server().run()


if __name__ == "__main__":
    main()
