"""Session folder management and visitor ID allocation.

Layout per session:
    sessions/
      session_YYYY-MM-DD_HH-MM-SS/
        audio/
        normalized/
        quality/
        transcripts/
        session.json
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class SessionPaths:
    root: Path
    audio: Path
    normalized: Path
    quality: Path
    transcripts: Path


def new_session_paths(sessions_root: Path) -> SessionPaths:
    sessions_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    root = sessions_root / f"session_{stamp}"
    paths = SessionPaths(
        root=root,
        audio=root / "audio",
        normalized=root / "normalized",
        quality=root / "quality",
        transcripts=root / "transcripts",
    )
    for d in (paths.audio, paths.normalized, paths.quality, paths.transcripts):
        d.mkdir(parents=True, exist_ok=True)
    return paths


class VisitorIdAllocator:
    """Thread-safe, monotonically increasing visitor ID allocator.

    IDs are zero-padded to four digits. Counter is persisted in session.json
    so the next session could pick up, but each session starts fresh.
    """

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
            vid = f"visitor_{self._next:04d}"
            self._next += 1
            return vid

    def peek(self) -> int:
        with self._lock:
            return self._next


def write_session_json(paths: SessionPaths, started_at: datetime) -> None:
    payload = {
        "session_id": paths.root.name,
        "started_at": started_at.isoformat(timespec="seconds"),
        "layout": {
            "audio": "audio/",
            "normalized": "normalized/",
            "quality": "quality/",
            "transcripts": "transcripts/",
        },
    }
    (paths.root / "session.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def list_wav_files(directory: Path) -> Iterator[Path]:
    return sorted(p for p in directory.glob("*.wav") if p.is_file())
