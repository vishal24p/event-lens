"""Read WAV duration without loading full audio into memory."""
from __future__ import annotations

from pathlib import Path


def read_wav_duration_seconds(wav_path: Path) -> float:
    try:
        import soundfile as sf

        with sf.SoundFile(str(wav_path), mode="r") as handle:
            if handle.samplerate:
                return float(handle.frames) / float(handle.samplerate)
    except Exception:
        pass
    return 0.0
