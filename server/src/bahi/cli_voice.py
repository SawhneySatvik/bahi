"""Push-to-talk CLI client for the Bahi server (`make smoke-voice`).

Records the mic with ffmpeg (macOS avfoundation / linux alsa), POSTs to
/api/turn/audio, prints the transcript + reply, plays the spoken answer.
"""

from __future__ import annotations

import argparse
import base64
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


def record(seconds: float, device: str) -> bytes:
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)  # noqa: SIM115
    out.close()
    if platform.system() == "Darwin":
        cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-i", device, "-t", str(seconds)]
    else:
        cmd = ["ffmpeg", "-y", "-f", "alsa", "-i", device or "default", "-t", str(seconds)]
    subprocess.run(
        [*cmd, "-ar", "16000", "-ac", "1", out.name],
        check=True,
        capture_output=True,
    )
    data = Path(out.name).read_bytes()
    Path(out.name).unlink(missing_ok=True)
    return data


def play(data: bytes, mime: str) -> None:
    suffix = ".mp3" if "mpeg" in mime else ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)  # noqa: SIM115
    tmp.write(data)
    tmp.close()
    player = ["afplay", tmp.name] if platform.system() == "Darwin" else ["aplay", tmp.name]
    subprocess.run(player, check=False, capture_output=True)
    Path(tmp.name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bahi.cli_voice")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--device", default=":0", help="ffmpeg input device (mac ':0')")
    parser.add_argument("--file", default=None, help="send an audio file instead of the mic")
    args = parser.parse_args(argv)

    client = httpx.Client(base_url=args.server, timeout=120)
    profile = client.get("/health").json()["profile"]
    print(f"connected · profile: stt={profile['stt']} tts={profile['tts']} "
          f"orchestrator={profile['orchestrator']}")

    while True:
        if args.file:
            audio = Path(args.file).read_bytes()
        else:
            input(f"\n[Enter] to record {args.seconds:.0f}s (Ctrl-C to quit) ")
            print("● recording…")
            audio = record(args.seconds, args.device)
        response = client.post(
            "/api/turn/audio", files={"file": ("utterance.wav", audio, "audio/wav")}
        )
        if response.status_code != 200:
            print(f"error {response.status_code}: {response.text[:300]}")
        else:
            body = response.json()
            print(f"heard  : {body['transcript']}")
            print(f"reply  : {body['reply']}")
            print(
                f"timing : stt={body['stt_seconds']}s total={body['total_seconds']}s "
                f"intents={body['intents']}"
            )
            play(base64.b64decode(body["reply_audio_b64"]), body["reply_audio_mime"])
        if args.file:
            break


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print()
