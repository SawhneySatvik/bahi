"""Bahi for Alexa+ — the ledger MCP server over Streamable HTTP (MCP spec 2025-11-25).

Same ledger tools as the stdio server, plus two voice-first tools built for a
smart speaker / Echo Show turn, where the owner asks one short question and
expects one short spoken answer:

- `shop_brief`      — "Alexa, ask Bahi how the shop is doing" → today's takings,
                      udhaar given, cash in, and the top people who owe money.
- `recent_activity` — "Alexa, ask Bahi what was the last entry" → the last few
                      ledger entries, so a mis-heard entry can be caught fast.

Each tool returns a `speech` field (one or two sentences an assistant can read
out as-is) next to the structured numbers, so the assistant never has to do
money arithmetic itself.

Run:  BAHI_MCP_PORT=8765 python -m bahi.mcp_server.http   → http://0.0.0.0:8765/mcp
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bahi.config import get_settings
from bahi.ledger.db import init_db, session_scope
from bahi.ledger.repository import LedgerRepository, rupees
from bahi.mcp_server.server import build_server

ToolResult = dict[str, Any]


def shop_brief(top_n: int = 3) -> ToolResult:
    """A short spoken brief of the shop today: sales, udhaar given, repayments,
    cash in, total outstanding udhaar and the top debtors. Use this when the owner
    asks "how is the shop doing" / "aaj ka hisaab batao"."""
    with session_scope() as session:
        repo = LedgerRepository(session, tz=get_settings().tz)
        day = repo.day_summary(None)
        debtors = sorted(repo.list_debtors(), key=lambda cb: -cb[1])
        outstanding = sum(b for _, b in debtors)
        top = [
            {"customer": c.name, "balance": rupees(b), "balance_paise": b}
            for c, b in debtors[:top_n]
        ]

    parts = [
        f"Today you sold {rupees(day['sales_paise'])}",
        f"gave {rupees(day['udhaar_given_paise'])} on udhaar",
        f"and collected {rupees(day['repayments_received_paise'])} in repayments,"
        f" so {rupees(day['cash_in_paise'])} cash came in.",
    ]
    speech = ", ".join(parts[:2]) + " " + parts[2]
    if top:
        names = ", ".join(f"{d['customer']} {d['balance']}" for d in top)
        speech += (
            f" {len(debtors)} people owe you {rupees(outstanding)} in total; the most is {names}."
        )
    else:
        speech += " Nobody owes you anything right now."
    return {
        "date": day["date"],
        "sales": rupees(day["sales_paise"]),
        "udhaar_given": rupees(day["udhaar_given_paise"]),
        "repayments_received": rupees(day["repayments_received_paise"]),
        "cash_in": rupees(day["cash_in_paise"]),
        "total_outstanding": rupees(outstanding),
        "debtor_count": len(debtors),
        "top_debtors": top,
        "speech": speech,
    }


def recent_activity(limit: int = 5) -> ToolResult:
    """The last few ledger entries, newest first, so the owner can check what was
    just written ("what was the last entry?")."""
    limit = max(1, min(limit, 20))
    with session_scope() as session:
        repo = LedgerRepository(session, tz=get_settings().tz)
        txns = repo.recent_transactions(limit)
        entries = [
            {
                "transaction_id": t.id,
                "type": t.type,
                "amount": rupees(t.amount_paise),
                "amount_paise": t.amount_paise,
                "customer": t.customer.name if t.customer else None,
                "note": t.note,
            }
            for t in txns
        ]
    if entries:
        last = entries[0]
        who = f" for {last['customer']}" if last["customer"] else ""
        speech = f"The last entry was a {last['type']} of {last['amount']}{who}."
    else:
        speech = "The ledger is empty."
    return {"entries": entries, "speech": speech}


VOICE_TOOL_FUNCTIONS = [shop_brief, recent_activity]


def build_http_server(host: str, port: int) -> Any:
    # Public behind a tunnel / load balancer: the Host header is the tunnel's, so
    # DNS-rebinding protection (on by default for 127.0.0.1) would reject it.
    server = build_server(
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for fn in VOICE_TOOL_FUNCTIONS:
        server.add_tool(fn)

    @server.custom_route("/", methods=["GET"])
    async def echo_show(_: Request) -> Response:
        # Simulated Echo Show: a browser MCP client against /mcp on this same origin.
        return HTMLResponse((Path(__file__).parent / "echo_show.html").read_text(encoding="utf-8"))

    return server


def main() -> None:
    init_db()
    host = os.environ.get("BAHI_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("BAHI_MCP_PORT", "8765"))
    build_http_server(host, port).run(transport="streamable-http")


if __name__ == "__main__":
    main()
