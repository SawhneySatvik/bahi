"""Generate synthetic eval audio: the CONFIGURED TTS speaks each audio-case's
utterance; files land in evals/audio/synthetic/. Reports label these clips
synthetic — when the TTS vendor matches the STT under test, that same-vendor
circularity is stated, not hidden. Self-recorded clips in evals/audio/recorded/
take precedence when present.

    set -a; . ./.env; . envs/sarvam.env; set +a
    python -m bahi.evals.audio_synth --suite audio_core
"""

from __future__ import annotations

import argparse

from bahi.config import get_settings
from bahi.evals.suite import load_suite, suite_path
from bahi.providers.factory import build_tts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bahi.evals.audio_synth")
    parser.add_argument("--suite", default="audio_core")
    args = parser.parse_args(argv)

    settings = get_settings()
    tts = build_tts(settings)
    suite = load_suite(suite_path(args.suite))
    audio_root = suite_path(args.suite).parents[1] / "audio"
    out_dir = audio_root / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for case in suite.cases:
        for index, turn in enumerate(case.turns):
            if not turn.audio:
                continue
            target = audio_root / turn.audio
            if "recorded/" in turn.audio:
                continue  # human-recorded clips are never overwritten
            speak = turn.tts_text or turn.gold_transcript or turn.utterance
            synthesis = tts.synthesize(speak, settings.reply_language)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(synthesis.audio.data)
            generated += 1
            print(f"  {case.id}[{index}] -> {target.name} ({len(synthesis.audio.data)}b)")
    print(f"generated {generated} clips with TTS={settings.tts_provider} "
          f"(label: synthetic, same-vendor circularity applies if STT vendor matches)")


if __name__ == "__main__":
    main()
