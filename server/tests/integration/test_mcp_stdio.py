"""The ledger as a REAL MCP server: spawn `python -m bahi.mcp_server` over
stdio and drive it with the official MCP client — the same path Claude Code
uses. Offline, deterministic, no keys."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_mcp_server_end_to_end(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path}/mcp.db"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "bahi.mcp_server"], env=env
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {
            "add_sale",
            "add_udhaar",
            "record_repayment",
            "get_balance",
            "list_debtors",
            "day_summary",
            "find_customer",
        } <= names

        result = await session.call_tool(
            "add_udhaar", {"customer_name": "Ramesh", "amount_paise": 20000}
        )
        assert not result.isError
        payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
        assert payload["new_balance_paise"] == 20000

        balance = await session.call_tool("get_balance", {"customer_name": "ramesh"})
        assert not balance.isError
        payload = json.loads(balance.content[0].text)  # type: ignore[union-attr]
        assert payload["balance_paise"] == 20000
        assert payload["balance"] == "₹200.00"
