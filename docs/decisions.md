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

## Phase 0.5 spike verdicts (2026-07-08, live API calls; fixtures in server/tests/fixtures/)

- **Sarvam chat tool-calling: CONFIRMED NATIVE** on both `sarvam-30b` and `sarvam-105b` —
  OpenAI-compatible request (`tools`, `tool_choice`) and response (`message.tool_calls[]`
  with `function.arguments` as a JSON *string* the adapter must parse). Auth for chat is
  `Authorization: Bearer`; speech uses `api-subscription-key`. No `base.py` change needed;
  the JSON-prompting fallback is retired.
- **Observed model-tier gap**: same prompt, 30B returned `amount_paise: 200` (unit error),
  105B returned `20000` (correct). Supports the 105B-orchestrator tiering and becomes a
  seeded eval case (rupee→paise conversion).
- **Bulbul v3**: returns base64 WAV in `audios[]` at **22050 Hz mono**; bulbul:v3 speaker
  list differs from v2 (`anushka` invalid → profile pins `priya`).
- **Saaras v3 codemix**: TTS→STT round-trip returned a perfect Devanagari transcript
  ("रमेश को दो सौ रुपये उधार लिख दो") — note full Devanagari output incl. number words;
  WER normalization (script folding, number-word folding) is mandatory for fair A/B.
- **Gemini 2.5 Flash**: function-calling PASS; `usageMetadata` splits `thoughtsTokenCount`
  (101 on this call) from `candidatesTokenCount` — adapter counts thoughts as billed
  output tokens in `LLMUsage`.
- ElevenLabs + OpenAI spikes: scripted, skip pending keys; must run before Phase 6 adapters.

## Amendments

- **2026-07-08 (Phase 2)** — `Message` gained `name: str | None` (tool name on
  `role="tool"` messages): Gemini's `functionResponse` keys tool results by *name*,
  not by call id. Sarvam/OpenAI ignore it and use `tool_call_id`. Purely additive.
- **2026-07-08 (Phase 2)** — Adapters use raw REST via httpx (no vendor SDKs at all):
  shapes are pinned by the Phase 0.5 fixtures, adapters stay transparent, and the
  no-SDK-outside-adapters rule is trivially true. httpx promoted to runtime dep.
- **2026-07-08 (Phase 2, live probe)** — Saaras codemix normalizes speech to symbols
  ("do sau rupaye" → "₹200") — WER normalizer must fold currency symbols and number
  words bidirectionally.
- **2026-07-08 (Phase 3, live smoke findings)** —
  (a) LLMs don't know today's date: insights agent passed a stale date to day_summary
  and got zeros → `prompts.today_line(tz)` appended to every system prompt at runtime.
  (b) 105B orchestrator can spiral into "verification" re-delegations → DelegateBoard
  dedupes identical (specialist, instruction) pairs (replays prior reply, guards the
  ledger against double writes) + prompt rule "one delegation per action".
  (c) sarvam-30b needed few-shot examples in specialist prompts to reliably record
  anonymous sales; 105B once leaked textual `<tool_call>` markup → no-markup prompt rule.
  (d) Gemini free tier is 5 RPM on gemini-2.5-flash (observed 429) → `_http.post_with_retry`
  honors 'retry in Ns'; committed Gemini profiles pin gemini-2.5-flash-lite (own quota
  bucket); flash remains one env var away. Eval runner must expect rate-limit pacing.
  (e) gemini-2.5-flash-lite sometimes returns empty text after tool results → TurnEngine
  falls back to the last specialist reply so a turn is never silent.
