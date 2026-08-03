"""Shared pytest fixtures and a fake transcription adapter."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional

import numpy as np
import pytest
import soundfile as sf

from src.stt.types import (
    Segment,
    TranscriptionAdapter,
    TranscriptionResult,
)


class FakeAdapter(TranscriptionAdapter):
    def __init__(self, fail_on: Optional[set[str]] = None) -> None:
        self.calls: List[Path] = []
        self._fail_on = fail_on or set()
        self._lock = threading.Lock()

    def transcribe(
        self, wav_path: Path, initial_prompt: str = ""
    ) -> TranscriptionResult:
        with self._lock:
            self.calls.append(Path(wav_path))
        vid = wav_path.stem
        if vid in self._fail_on:
            raise RuntimeError(f"forced failure for {vid}")
        return TranscriptionResult(
            language="en",
            text=f"transcribed {vid}",
            segments=[Segment(start=0.0, end=1.0, text=f"transcribed {vid}")],
        )


def _write_sine(path: Path, seconds: float = 1.0, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, seconds, int(seconds * sr), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(str(path), samples, sr, subtype="PCM_16")


@pytest.fixture()
def sine_factory(tmp_path):
    def _make(name: str, seconds: float = 1.0, sr: int = 16000) -> Path:
        return tmp_path / name

    return _make
