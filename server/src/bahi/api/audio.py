"""The audio-format boundary: whatever the client recorded (browser webm/opus,
m4a, anything ffmpeg reads) is normalized to canonical 16kHz mono PCM WAV
BEFORE any STT adapter sees it — provider swaps can never leak format
requirements into the client.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from bahi.providers.base import AudioChunk

CANONICAL_RATE = 16000


class TranscodeError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def to_canonical_wav(data: bytes, mime: str = "application/octet-stream") -> AudioChunk:
    """Any input container/codec -> 16kHz mono 16-bit PCM WAV.

    The output MUST be a seekable temp file, not pipe:1 — ffmpeg cannot
    rewrite the RIFF header on a pipe and emits the 0xFFFFFFFF streaming
    sentinel, which at least one vendor's billing precheck reads as a
    multi-gigabyte file and rejects with 'No credits available' (found live).
    """
    if not data:
        raise TranscodeError("empty audio payload")
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)  # noqa: SIM115
    out.close()
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", "pipe:0",
                "-ar", str(CANONICAL_RATE),
                "-ac", "1",
                "-c:a", "pcm_s16le",
                out.name,
            ],
            input=data,
            capture_output=True,
            timeout=30,
            check=False,
        )
        wav = Path(out.name).read_bytes()
    except FileNotFoundError as exc:
        raise TranscodeError("ffmpeg not installed — required for the audio path") from exc
    except subprocess.TimeoutExpired as exc:
        raise TranscodeError("audio transcode timed out (30s)") from exc
    finally:
        Path(out.name).unlink(missing_ok=True)
    if proc.returncode != 0 or not wav:
        raise TranscodeError(
            f"could not decode audio ({mime}): {proc.stderr.decode(errors='replace')[:300]}"
        )
    return AudioChunk(data=wav, mime="audio/wav", sample_rate=CANONICAL_RATE, channels=1)
