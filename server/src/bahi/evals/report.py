"""Render eval results as Markdown. One file = one profile column; several
files = the A/B comparison table (same suite, different profiles).

    python -m bahi.evals.report results/a.json results/b.json [-o report.md]
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

PCT_METRICS = [
    ("intent_accuracy", "Intent accuracy"),
    ("tool_correctness", "Tool-call correctness"),
    ("ledger_match", "Ledger-state match"),
    ("task_success", "Task success"),
]
RAW_METRICS = [
    ("latency_p50", "Latency p50 (s)"),
    ("latency_p95", "Latency p95 (s)"),
    ("llm_seconds_p50", "LLM time p50 (s)"),
    ("cost_per_turn_inr", "Cost / turn (₹)"),
    ("total_cost_inr", "Suite cost (₹)"),
]


def _metric(payload: dict[str, Any], key: str) -> str:
    values = [run["aggregates"][key] for run in payload["runs"]]
    mean = statistics.mean(values)
    is_pct = key in {k for k, _ in PCT_METRICS}
    rendered = f"{mean:.1%}" if is_pct else f"{mean:.2f}"
    if len(values) > 1:
        spread = (max(values) - min(values)) / 2
        rendered += f" ± {spread:.1%}" if is_pct else f" ± {spread:.2f}"
    return rendered


def _failures(payload: dict[str, Any]) -> list[str]:
    lines = []
    for run in payload["runs"]:
        for case in run["cases"]:
            for turn in case["turns"]:
                if not turn["task_ok"] or not turn["intents_ok"] or not turn["tools_ok"]:
                    what = [
                        name
                        for name, ok in [
                            ("intent", turn["intents_ok"]),
                            ("tools", turn["tools_ok"]),
                            ("ledger", turn["ledger_ok"]),
                            ("reply", bool(turn["detail"]["reply"].strip())),
                        ]
                        if not ok
                    ]
                    lines.append(
                        f"- `{case['id']}` (run {run['repeat']}) — failed {', '.join(what)}: "
                        f"\"{turn['utterance']}\" → intents={turn['detail']['intents']}, "
                        f"tools={turn['detail']['called_tools']}, "
                        f"delta={turn['detail']['delta']} "
                        f"(expected {turn['detail']['expected_delta']})"
                    )
    return lines


def render(payloads: list[dict[str, Any]]) -> str:
    labels = [p["label"] for p in payloads]
    first = payloads[0]
    lines = [
        f"# Bahi eval report — suite `{first['suite']}`",
        "",
        f"Generated {first['timestamp']} · repeats: "
        + ", ".join(str(p["repeats"]) for p in payloads)
        + f" · temperature 0 · FX pinned ₹{first['fx_inr_per_usd']:.0f}/USD "
        f"(prices dated {first['prices_dated']})",
        "",
        "| Profile | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]
    for row_label, payload_key in [
        ("Orchestrator", "orchestrator"),
        ("Specialist", "specialist"),
        ("Routing", "routing"),
    ]:
        values = [
            p["profile"].get(payload_key, p.get(payload_key, "?")) if payload_key != "routing"
            else p.get("routing", "?")
            for p in payloads
        ]
        lines.append(f"| {row_label} | " + " | ".join(str(v) for v in values) + " |")
    lines += ["", "| Metric | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for key, name in PCT_METRICS + RAW_METRICS:
        lines.append(f"| {name} | " + " | ".join(_metric(p, key) for p in payloads) + " |")
    if any(p["runs"][0]["aggregates"].get("wer_mean") is not None for p in payloads):
        wer_cells = []
        for p in payloads:
            agg = p["runs"][0]["aggregates"]
            wer_cells.append(
                f"{agg['wer_mean']:.1%} ({agg['audio_turns']} clips)"
                if agg.get("wer_mean") is not None
                else "—"
            )
        lines.append("| WER, normalized (audio) | " + " | ".join(wer_cells) + " |")
    turns = [str(p["runs"][0]["aggregates"]["turns"]) for p in payloads]
    lines.append("| Turns evaluated | " + " | ".join(turns) + " |")

    for payload in payloads:
        failures = _failures(payload)
        if failures:
            lines += ["", f"## Failures — {payload['label']}", *failures]
    lines += [
        "",
        "_Metrics: intent = gold specialists routed; tools = required tools called and no "
        "unexpected ledger writes; ledger = canonical delta multiset equality (type, paise, "
        "normalized customer; ids/timestamps ignored); task = ledger ok + non-empty reply._",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bahi.evals.report")
    parser.add_argument("results", nargs="+", help="result JSON file(s)")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)
    payloads = [json.loads(Path(p).read_text()) for p in args.results]
    markdown = render(payloads)
    print(markdown)
    if args.out:
        Path(args.out).write_text(markdown)


if __name__ == "__main__":
    main()
