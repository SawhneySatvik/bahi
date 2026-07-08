# Bahi eval metrics — definitions

The single source of truth for what "correct" means. The eval runner and the
manual smoke scripts share these comparators (`bahi/evals/metrics.py`).

## Per-turn checks

| Metric | Definition |
|---|---|
| **Intent accuracy** | Gold specialists ⊆ routed specialists. `gold_intents_any` = at least one listed intent routed (`none` sentinel accepts an un-delegated turn — used where khata/insights overlap by design, or where a clarifying question at either level is correct). Empty gold = nothing may be delegated. |
| **Tool-call correctness** | Every `expected_tools` entry was called, AND no *mutating* tool (`add_sale`, `add_udhaar`, `record_repayment`) was called beyond those expected — unless the ledger refused it (error result, no write): an attempted-and-refused mutation is legitimate discovery. Extra reads are free. |
| **Ledger-state match** | Canonical delta multiset equality. A write is `(type, amount_paise, normalized_customer_or_None)`; ids and timestamps ignored; customer names compared casefolded + whitespace-collapsed. Multiset: a duplicate write fails. `[]` = the turn must write nothing (error handling, clarifications, reads). |
| **Task success** | Ledger-state match AND a non-empty spoken reply. |

## Latency & cost

- Latency = wall-clock per turn (`p50`/`p95` over all turns), plus LLM-only time
  (sum of LLM hop durations) to separate model time from tool/DB time.
- Cost = per-model token prices in `evals/cost.py`, INR-pinned (FX rate and
  price date printed in every report). Unknown models are reported as
  *unpriced*, never silently ₹0.

## Reproducibility

- temperature 0 everywhere; model versions pinned in `envs/*.env`.
- `--repeats N` reports mean ± half-range across runs.
- Free-tier rate limits: adapters retry 429/5xx honoring the server's
  suggested delay; `--sleep` paces between cases.

## What good evals look like (vs noise) — working notes

- Score against **ground truth the system itself produced** (the ledger rows),
  not string-matched replies. Reply wording varies run to run; a ₹200 udhaar row
  either exists or it doesn't.
- **Penalize unexpected writes**, not just missing ones — a double-recorded sale
  is worse than a missed one in a money system.
- Overlapping routes are **design facts, not scoring errors** — encode them
  (`gold_intents_any`) instead of forcing a fake single label.
- Error-handling cases (`repayment_exceeds_balance`) assert the *absence* of a
  write. A harness that only checks happy paths measures nothing.
