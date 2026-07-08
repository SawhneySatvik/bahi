# Bahi eval report — suite `core`

Generated 2026-07-08T03:36:40 · repeats: 1, 1 · temperature 0 · FX pinned ₹90/USD (prices dated 2026-07-08)

| Profile | sarvam | sarvam-direct |
|---|---|---|
| Orchestrator | sarvam:sarvam-105b | sarvam:sarvam-105b |
| Specialist | sarvam:sarvam-30b | sarvam:sarvam-30b |
| Routing | delegated | direct |

| Metric | sarvam | sarvam-direct |
|---|---|---|
| Intent accuracy | 100.0% | 100.0% |
| Tool-call correctness | 97.6% | 97.6% |
| Ledger-state match | 97.6% | 95.2% |
| Task success | 95.2% | 95.2% |
| Latency p50 (s) | 3.69 | 1.85 |
| Latency p95 (s) | 9.48 | 8.59 |
| LLM time p50 (s) | 3.68 | 1.84 |
| Cost / turn (₹) | 0.02 | 0.01 |
| Suite cost (₹) | 0.80 | 0.52 |
| Turns evaluated | 42 | 42 |

## Failures — sarvam
- `repayment_unknown_customer` (run 0) — failed tools: "Ghost ne 100 rupaye wapas kiye" → intents=['khata'], tools=['delegate_khata', 'find_customer', 'record_repayment'], delta=[] (expected [])
- `sale_fractional_rupees` (run 0) — failed ledger, reply: "sadhe bara rupaye ki sale likho" → intents=['billing'], tools=['add_sale', 'delegate_billing'], delta=[['sale', 5000, None]] (expected [['sale', 1250, None]])
- `sale_then_summary` (run 0) — failed reply: "100 ki sale likh ke aaj ka total batao" → intents=['billing'], tools=['add_sale', 'delegate_billing'], delta=[['sale', 10000, None]] (expected [['sale', 10000, None]])

## Failures — sarvam-direct
- `repayment_unknown_customer` (run 0) — failed tools: "Ghost ne 100 rupaye wapas kiye" → intents=['khata'], tools=['record_repayment'], delta=[] (expected [])
- `sale_number_words_250` (run 0) — failed ledger: "dhai sau rupaye ki sale hui" → intents=['billing'], tools=['add_sale'], delta=[['sale', 50000, None]] (expected [['sale', 25000, None]])
- `sale_fractional_rupees` (run 0) — failed ledger: "sadhe bara rupaye ki sale likho" → intents=['billing'], tools=['add_sale'], delta=[['sale', 50000, None]] (expected [['sale', 1250, None]])

_Metrics: intent = gold specialists routed; tools = required tools called and no unexpected ledger writes; ledger = canonical delta multiset equality (type, paise, normalized customer; ids/timestamps ignored); task = ledger ok + non-empty reply._