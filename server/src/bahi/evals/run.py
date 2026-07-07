"""CLI: run one suite against the CURRENTLY CONFIGURED profile.

    set -a; . ./.env; . envs/sarvam.env; set +a
    python -m bahi.evals.run --suite core --label sarvam [--repeats 1] [--sleep 0]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bahi.evals.runner import run_suite
from bahi.evals.suite import load_suite, suite_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bahi.evals.run")
    parser.add_argument("--suite", default="core")
    parser.add_argument("--label", required=True, help="profile label for the report column")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between cases")
    parser.add_argument(
        "--results-dir", default=str(Path(__file__).parents[3] / "evals" / "results")
    )
    args = parser.parse_args(argv)

    suite = load_suite(suite_path(args.suite))
    print(f"suite {suite.suite}: {len(suite.cases)} cases · label={args.label}")
    payload = run_suite(
        suite,
        label=args.label,
        repeats=args.repeats,
        sleep_s=args.sleep,
        results_dir=Path(args.results_dir),
    )
    aggregates = payload["runs"][0]["aggregates"]
    print(
        f"\nintent={aggregates['intent_accuracy']:.1%} "
        f"tools={aggregates['tool_correctness']:.1%} "
        f"ledger={aggregates['ledger_match']:.1%} "
        f"task={aggregates['task_success']:.1%} "
        f"p50={aggregates['latency_p50']:.2f}s p95={aggregates['latency_p95']:.2f}s "
        f"cost/turn=₹{aggregates['cost_per_turn_inr']}"
    )


if __name__ == "__main__":
    main()
