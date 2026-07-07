"""Live one-shot probes against the CONFIGURED providers (manual, real APIs).

    python -m bahi.probes tts "Ramesh ko 200 rupaye udhaar likh do" out.wav
    python -m bahi.probes stt out.wav
    python -m bahi.probes llm "Ramesh ko 200 rupaye udhaar likh do" --role orchestrator

The llm probe advertises the REAL ledger tool specs and prints any tool calls
(it does not execute them — that is the Phase 3 agent loop's job).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from bahi.config import get_settings
from bahi.mcp_server.tools import ledger_tool_registry
from bahi.providers.base import AudioChunk, Message
from bahi.providers.factory import build_llm, build_stt, build_tts


def _probe_tts(text: str, out_path: str) -> None:
    settings = get_settings()
    tts = build_tts(settings)
    start = time.perf_counter()
    synthesis = tts.synthesize(text, settings.reply_language)
    elapsed = time.perf_counter() - start
    pathlib.Path(out_path).write_bytes(synthesis.audio.data)
    print(f"provider={settings.tts_provider} chars={synthesis.usage.characters}")
    print(f"audio: {len(synthesis.audio.data)} bytes {synthesis.audio.mime} "
          f"{synthesis.audio.sample_rate}Hz -> {out_path}")
    print(f"latency: {elapsed:.2f}s")


def _probe_stt(file_path: str) -> None:
    settings = get_settings()
    stt = build_stt(settings)
    data = pathlib.Path(file_path).read_bytes()
    audio = AudioChunk(data=data, mime="audio/wav")
    start = time.perf_counter()
    transcript = stt.transcribe(audio, settings.language)
    elapsed = time.perf_counter() - start
    print(f"provider={settings.stt_provider} language={transcript.language}")
    print(f"transcript: {transcript.text}")
    print(f"audio_seconds={transcript.usage.audio_seconds:.2f} latency: {elapsed:.2f}s")


def _probe_llm(utterance: str, role: str) -> None:
    settings = get_settings()
    llm, model = build_llm(settings, role)  # type: ignore[arg-type]
    tools = ledger_tool_registry().specs()
    messages = [
        Message(
            role="system",
            content="You manage a kirana shop ledger. Amounts are integer paise "
            "(₹1 = 100 paise). Use tools to record what the shopkeeper says.",
        ),
        Message(role="user", content=utterance),
    ]
    start = time.perf_counter()
    turn = llm.complete(messages, tools, model=model, temperature=0.0)
    elapsed = time.perf_counter() - start
    print(f"provider={llm.name} model={turn.model}")
    print(f"content: {turn.content!r}")
    for tc in turn.tool_calls:
        print(f"tool_call: {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})")
    print(f"usage: in={turn.usage.input_tokens} out={turn.usage.output_tokens}")
    print(f"latency: {elapsed:.2f}s")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bahi.probes")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tts = sub.add_parser("tts")
    p_tts.add_argument("text")
    p_tts.add_argument("out", nargs="?", default="probe_out.wav")

    p_stt = sub.add_parser("stt")
    p_stt.add_argument("file")

    p_llm = sub.add_parser("llm")
    p_llm.add_argument("utterance")
    p_llm.add_argument("--role", choices=["orchestrator", "specialist"], default="orchestrator")

    args = parser.parse_args(argv)
    if args.cmd == "tts":
        _probe_tts(args.text, args.out)
    elif args.cmd == "stt":
        _probe_stt(args.file)
    elif args.cmd == "llm":
        _probe_llm(args.utterance, args.role)


if __name__ == "__main__":
    main(sys.argv[1:])
