# Bahi

**A voice-first, multilingual shop manager for kirana / small-retail owners — built to run on any voice/LLM vendor's stack, selected by config, not code.**

The shopkeeper speaks in their own language ("Ramesh ko do sau rupaye udhaar likh do"). An orchestrator routes the turn to specialist agents — **khata** (credit ledger), **billing**, **insights** — that update the shop's books and speak back a real summary ("aaj ka hisaab batao" → today's takings and who owes what). The name comes from *bahi-khata*, the traditional Indian ledger.

Bahi's defining constraint is **total plug-and-play**: every model/vendor capability (speech-to-text, text-to-speech, LLM chat + tool-calling, vision) lives behind a provider interface chosen by an environment variable. Swapping from Sarvam to ElevenLabs to OpenAI to a local model is a config change — never an edit to the orchestrator, agents, ledger, or eval harness. Two full provider stacks ship today (**Sarvam** and **ElevenLabs**), with **Gemini** and **OpenAI** for LLM breadth.

Built with [Claude Code](https://claude.com/claude-code).

---

## Why it's built this way

- **Provider-blind core.** The orchestrator, specialist agents, ledger, and eval harness speak only to `STTProvider` / `TTSProvider` / `LLMProvider` / `VisionProvider` protocols. No vendor SDK is imported outside its adapter module — a test (`test_no_network_imports.py`) enforces it.
- **Config-selected everything.** A "provider swap" is just exporting different env vars. Committed profiles in `envs/*.env` are ready-made stacks; secrets stay in a gitignored `.env`.
- **Per-role LLMs, cross-vendor mixing first-class.** The orchestrator and specialists can run different models from different vendors (e.g. a bigger orchestrator model, a cheaper specialist). The `mixed` profile does exactly this.
- **Data stays local.** The ledger (SQLite by default, Postgres via `DATABASE_URL`) never leaves the machine except as tool results the LLM explicitly requested — this keeps a sovereign / on-prem deployment story truthful.
- **Eval-first definition of done.** Nothing is "done" until it moves a number in the eval harness. The *same* YAML suite runs across every provider and produces an apples-to-apples A/B report (accuracy, tool-call correctness, ledger-state task success, WER, latency p50/p95, INR cost).

## Architecture

```
Interface layer      Voice loop + Next.js console  (mode: online | sovereign/local)
        │
Core agent layer     Orchestrator → specialist agents (khata, billing, insights)
        │            provider-blind; talks only to interfaces + tools
        │
Tools / backend      Shop ledger (SQLite/Postgres) exposed as callable MCP tools
        │
Providers layer      STT / TTS / LLM / Vision protocols + swappable adapters
                     (sarvam, elevenlabs, google, openai, fake)  ← config-selected
        │
Eval harness         YAML suites → same suite across providers →
                     intent accuracy · tool-call correctness · ledger task success ·
                     WER · latency p50/p95 · cost (INR)
```

A single voice turn: **audio in** → STT → orchestrator LLM (routes) → specialist LLM (calls ledger tools) → ledger write/read → reply text → TTS → **audio out**. Turn-based push-to-talk; audio transcoding is isolated at the API boundary (ffmpeg), so the core only ever sees canonical PCM/WAV.

## Repository layout

```
server/                 Python 3.12 · FastAPI · the whole backend + core
  src/bahi/
    api/                FastAPI app, audio (voice) endpoint, ledger endpoint
    core/               orchestrator, agent loop, voice loop, prompts
    ledger/             SQLAlchemy models, repository, DB (paise as integers)
    mcp_server/         ledger tools defined once (FastMCP); in-proc + stdio server
    providers/          base protocols, registry/factory, and per-vendor adapters:
                        sarvam/  elevenlabs/  google/  openai_/  fake/
    evals/              YAML suite runner, canonical metrics, WER, INR cost, A/B report
  tests/                unit · integration · provider-contract · fixtures
  alembic/              ledger migrations
  evals/suites/         core.yaml, audio_core.yaml
client/                 Next.js + TypeScript voice console (push-to-talk UI + live khata panel)
envs/                   committed provider profiles: offline · sarvam · elevenlabs · mixed
docs/                   decisions.md (locked design log) · metrics.md (what "correct" means)
Makefile                every workflow (setup / run / test / eval / probes / client / mcp)
.env.example            copy to .env; fill only the keys your profile needs
```

## Providers

| Capability | Adapters shipped |
|---|---|
| STT | `sarvam` (Saaras v3, codemix), `elevenlabs` (Scribe), `fake` |
| TTS | `sarvam` (Bulbul v3), `elevenlabs` (Flash v2.5), `fake` |
| LLM (chat + tool-calling) | `sarvam` (105B / 30B), `google` (Gemini 2.5 Flash), `openai` (GPT-5.4-mini), `fake` |
| Vision | `fake` (receipt/shelf reading is on the roadmap) |

The `fake` stack is deterministic and network-free — it's the default, so tests and the full agent loop run with no keys and no calls.

## Quick start

Requires **Python 3.12**, **Node** (for the client), and **ffmpeg** (for the voice loop).

```bash
# 1. install the server (creates server/.venv, editable install with dev deps)
make setup

# 2. run entirely offline — no API keys, deterministic fake providers
make run                       # FastAPI on http://localhost:8000  (PROFILE=offline)

# 3. run on a real vendor stack
cp .env.example .env           # then fill only the keys your profile needs
make run PROFILE=sarvam        # or: elevenlabs | mixed
```

Profiles are just env files: `make run PROFILE=sarvam` sources `envs/sarvam.env` (provider/model selections, no secrets) on top of your gitignored `.env` (keys). That layering *is* the provider swap.

### The voice console

```bash
make run PROFILE=sarvam        # backend on :8000
make client                    # Next.js console on :3000 (proxies /api + /health to :8000)
```

Push-to-talk mic, a transcript thread with per-hop latency and intent stamps, reply-audio playback, a text fallback, and a live khata panel (today's figures, balances, recent entries).

## Development

```bash
make check                     # the phase-gate trio: ruff lint + mypy (strict) + pytest
make lint                      # ruff
make typecheck                 # mypy --strict
make test                      # pytest
make test-one T=tests/unit/test_config.py::test_defaults_are_offline_fake
make client-check              # client gate: eslint + tsc + production build
```

### Live provider probes

```bash
make probe-llm PROFILE=sarvam TEXT="Ramesh ko 200 udhaar likho"
make probe-tts PROFILE=sarvam TEXT="aaj ka hisaab" OUT=out.wav
make probe-stt PROFILE=sarvam FILE=out.wav
```

### Ledger as a standalone MCP server

The ledger tools are defined once and exposed both in-process to the agent loop and as a standalone stdio MCP server:

```bash
make mcp                       # run the ledger as an MCP server over stdio
make migrate                   # apply alembic migrations to DATABASE_URL
```

## Evaluation

The same YAML suite runs against any profile and scores against **ground truth the system itself produced** — the actual ledger rows — not string-matched replies.

```bash
make eval PROFILE=sarvam SUITE=core          # run one suite against one profile
make eval PROFILE=sarvam SUITE=core REPEATS=3 SLEEP=1   # variance across repeats
make eval-report RESULTS="server/evals/results/a.json server/evals/results/b.json"
make eval-audio-synth SUITE=audio_core       # synthesize eval audio with the profile's TTS
```

Metrics (defined once in `evals/metrics.py`, documented in `docs/metrics.md`):

- **Intent accuracy** — did the orchestrator route to the right specialist(s)?
- **Tool-call correctness** — were the required tools called, and were *no* unexpected mutating writes made? (a double-recorded sale is worse than a missed one in a money system)
- **Ledger-state match** — canonical delta multiset equality: a write is `(type, amount_paise, normalized_customer)`; ids/timestamps ignored, names casefolded.
- **Task success** — ledger match *and* a non-empty spoken reply.
- **Latency** p50/p95 (wall-clock and LLM-only), **cost** per turn in INR (FX + price date printed in every report).

Reproducibility: temperature 0 everywhere, models pinned in `envs/*.env`, `--repeats N` reports mean ± half-range.

**Latest `core` suite (42 turns, all-Sarvam, delegated routing):**

| Metric | Result |
|---|---|
| Intent accuracy | 100.0% |
| Tool-call correctness | 97.6% |
| Ledger-state match | 97.6% |
| Task success | 95.2% |
| Latency p50 / p95 | 3.69s / 9.48s |
| Cost / turn | ₹0.02 |

## Design decisions

Locked design choices and the research behind them live in [`docs/decisions.md`](docs/decisions.md); metric definitions in [`docs/metrics.md`](docs/metrics.md). Highlights: hand-rolled protocols + lazy registry (no LiteLLM/LangChain), env-only config, integer paise for money, MCP tools defined once, and a data boundary that keeps the ledger local-capable for a sovereign deployment.

## Roadmap

- Vision: receipt / shelf reading (`VisionProvider` interface exists; only the `fake` adapter ships today)
- Streaming / real-time voice (current loop is turn-based push-to-talk)
- On-device / on-prem "sovereign" provider stack (the abstraction already allows it)
- Deployment target: Vercel (Neon Postgres) attempted first, Cloud Run as fallback
