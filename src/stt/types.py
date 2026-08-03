"""Shared STT result types used by the processing worker."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Protocol


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    language: str
    text: str
    segments: List[Segment]


class TranscriptionAdapter(Protocol):
    def transcribe(self, wav_path: Path, initial_prompt: str = "") -> TranscriptionResult: ...
