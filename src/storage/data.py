"""Global on-disk storage for capture, processing, and reports."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataPaths:
    root: Path
    audio: Path
    normalized: Path
    quality: Path
    transcripts: Path
    reports: Path
    queue: Path


def data_paths(data_root: Path) -> DataPaths:
    root = data_root.resolve()
    paths = DataPaths(
        root=root,
        audio=root / "audio",
        normalized=root / "normalized",
        quality=root / "quality",
        transcripts=root / "transcripts",
        reports=root / "reports",
        queue=root / "queue.json",
    )
    for directory in (paths.audio, paths.normalized, paths.quality, paths.transcripts, paths.reports):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def next_visitor_number(audio_dir: Path) -> int:
    highest = 0
    for path in audio_dir.glob("visitor_*.wav"):
        match = re.fullmatch(r"visitor_(\d+)\.wav", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


class VisitorIdAllocator:
    """Thread-safe global, monotonically increasing visitor ID allocator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: int = 1

    def reset(self, start: int = 1) -> None:
        with self._lock:
            self._next = start

    def current(self) -> str:
        with self._lock:
            return f"visitor_{self._next:04d}"

    def allocate(self) -> str:
        with self._lock:
            visitor_id = f"visitor_{self._next:04d}"
            self._next += 1
            return visitor_id
