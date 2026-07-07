# Bahi — Decision Log

Locked with the user on 2026-07-08 (5 Q&A rounds), adversarially reviewed (Opus architect,
17 findings folded in), provider facts verified by a 105-agent deep-research sweep.
Amendments land here with a date and a reason — especially any `providers/base.py`
contract change forced by a real API surprise (see Phase 0.5 spike).

## Locked decisions

| Area | Decision |
|---|---|
| Runtime | Python 3.12 + venv (server/, FastAPI); Next.js + TS (client/) |
| Config | Env vars only; `envs/*.env` committed profiles (no secrets); `.env` for keys |
| Abstraction | Hand-rolled Protocols (STT/TTS/LLM/Vision) + lazy registry; no LiteLLM/LangChain |
| Usage/cost | Per-capability tagged Usage union (tokens vs audio-seconds vs characters); INR reporting with pinned FX |
| LLM roles | Per-role provider+model: orchestrator (sarvam-105b default) / specialist (sarvam-30b default) |
| MCP | Ledger tools defined once (FastMCP); in-process for the agent loop; standalone stdio server |
| Agents | Orchestrator + khata + billing + insights; `BAHI_ROUTING=delegated\|direct` |
| Ledger | SQLite + SQLAlchemy 2.0 + Alembic; Postgres via DATABASE_URL; integer paise |
| Data boundary | Ledger never leaves the machine except as tool results the LLM requested |
| Voice | Turn-based push-to-talk; ffmpeg transcode boundary in api/; p50 ≤ 3.5s with per-hop budgets |
| Language | Core-neutral `BAHI_LANG_HINTS` + `BAHI_CODEMIX`; vendor modes stay in adapters |
| Evals | Hand-rolled YAML runner; `given:`/`turns:[]`; canonical delta equality; temp=0, pinned models, N-repeat variance |
| Providers | Sarvam + Gemini first; ElevenLabs (components only) + OpenAI breadth; ElevenAgents = stretch demo |
| Deploy | Makefile local; Vercel attempted first (Neon Postgres, 4.5MB body cap, 10s/60s timeout risk); Cloud Run fallback |
| Scope | MVP = 2 full profiles + A/B eval report + MCP server + deployed console; Vision/streaming/on-device = roadmap |
| Git | Local from Phase 0, conventional commits, publish at MVP |

## Key research verdicts (2026-07-08, primary sources)

- Saaras v3 `mode=codemix` confirmed; Bulbul v3 current TTS.
- Sarvam chat tool-calling: docs show OpenAI-compatible `tools`/`tool_choice`/`tool_calls`;
  unconfirmed by adversarial pass → Phase 0.5 spike settles it; JSON-prompting fallback
  pre-registered inside the adapter.
- ElevenLabs: pin `scribe_v2` (v1 removed 2026-07-09); Flash v2.5 supports Hindi, has NO
  codemix mode (auto-detect only); $0.22/hr STT, $0.05/1K chars TTS.
- Gemini: default pin `gemini-2.5-flash` ($0.30/$2.50 per M, free tier, native function calling).
- Vercel Python: feasible w/ caveats — 4.5MB body cap, 10s (Hobby)/60s (Pro) timeout,
  ephemeral FS → Neon Postgres required. Go/no-go at Phase 8 vs measured turn latency.
- OpenAI (verified 2026-07-08, developers.openai.com): small tier = `gpt-5.4-mini`
  ($0.75 / $0.075 cached / $4.50 per 1M) and `gpt-5.4-nano` ($0.20/$1.25); `gpt-4o-mini`
  EOL (snapshots shut down 2026-07-23). Chat Completions `tools`/`tool_choice`/`tool_calls`
  still supported (Responses API recommended for new builds, but CC is the thinner,
  more portable adapter surface). GOTCHA: 5.4 models don't support tool calling with
  `reasoning: none` — the adapter must not send it. Default pin: `gpt-5.4-mini`.

## Amendments

*(none yet)*
