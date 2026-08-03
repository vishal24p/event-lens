"""Durable FIFO queue of accepted recordings waiting for processing."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


STATUS_PENDING = "pending"
STATUS_NORMALIZING = "normalizing"
STATUS_TRANSCRIBING = "transcribing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

ALL_STATUSES = {
    STATUS_PENDING,
    STATUS_NORMALIZING,
    STATUS_TRANSCRIBING,
    STATUS_COMPLETED,
    STATUS_FAILED,
}


@dataclass
class QueueItem:
    visitor_id: str
    raw_audio_path: Path
    status: str = STATUS_PENDING
    error: str = ""

    def snapshot(self) -> dict:
        return {
            "visitor_id": self.visitor_id,
            "raw_audio_path": str(self.raw_audio_path),
            "status": self.status,
            "error": self.error,
        }


class ProcessingQueue:
    """Thread-safe FIFO persisted as one local JSON file when configured."""

    def __init__(self, *, state_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._items: List[QueueItem] = []
        self._state_path = state_path
        if state_path is not None:
            self._restore()

    def enqueue(self, item: QueueItem) -> None:
        with self._lock:
            if item.status != STATUS_PENDING:
                raise ValueError("enqueue requires pending status")
            self._items.append(item)
            self._persist_locked()

    def pop_pending(self) -> Optional[QueueItem]:
        """Return the first pending item. Does not change its status."""
        with self._lock:
            for item in self._items:
                if item.status == STATUS_PENDING:
                    return item
        return None

    def set_status(
        self, visitor_id: str, status: str, error: str = ""
    ) -> None:
        if status not in ALL_STATUSES:
            raise ValueError(f"unknown status: {status}")
        with self._lock:
            for item in self._items:
                if item.visitor_id == visitor_id:
                    item.status = status
                    item.error = error
                    self._persist_locked()
                    return
        raise KeyError(visitor_id)

    def has_in_flight(self) -> bool:
        """True if any item is in normalizing/transcribing (i.e. worker is busy)."""
        with self._lock:
            return any(
                i.status in (STATUS_NORMALIZING, STATUS_TRANSCRIBING)
                for i in self._items
            )

    def has_pending(self) -> bool:
        with self._lock:
            return any(i.status == STATUS_PENDING for i in self._items)

    def has_open_work(self) -> bool:
        """True if anything is queued or in flight."""
        with self._lock:
            return any(
                i.status in (STATUS_PENDING, STATUS_NORMALIZING, STATUS_TRANSCRIBING)
                for i in self._items
            )

    def counts(self) -> dict:
        out = {s: 0 for s in ALL_STATUSES}
        with self._lock:
            for i in self._items:
                out[i.status] += 1
        return out

    def current_processing(self) -> Optional[QueueItem]:
        with self._lock:
            for item in self._items:
                if item.status in (STATUS_NORMALIZING, STATUS_TRANSCRIBING):
                    return item
        return None

    def failed_items(self) -> List[QueueItem]:
        with self._lock:
            return [i for i in self._items if i.status == STATUS_FAILED]

    def items(self) -> Iterator[QueueItem]:
        with self._lock:
            return iter(list(self._items))

    def snapshot_json(self) -> str:
        with self._lock:
            return json.dumps(
                {"items": [i.snapshot() for i in self._items]}, indent=2
            )

    def _restore(self) -> None:
        assert self._state_path is not None
        root = self._state_path.parent
        transcripts_dir = root / "transcripts"
        persisted_items: list[dict] = []
        if self._state_path.is_file():
            try:
                payload = json.loads(self._state_path.read_text(encoding="utf-8"))
                persisted_items = payload.get("items", [])
                if not isinstance(persisted_items, list):
                    persisted_items = []
            except (OSError, json.JSONDecodeError):
                persisted_items = []

        known_ids = set()
        for payload in persisted_items:
            if not isinstance(payload, dict):
                continue
            visitor_id = payload.get("visitor_id")
            raw_audio_file = payload.get("raw_audio_file")
            status = payload.get("status")
            error = payload.get("error", "")
            if not isinstance(visitor_id, str) or not isinstance(raw_audio_file, str):
                continue
            if (
                Path(raw_audio_file).name != raw_audio_file
                or not isinstance(status, str)
                or status not in ALL_STATUSES
            ):
                continue
            raw_path = root / "audio" / raw_audio_file
            transcript_exists = (transcripts_dir / f"{visitor_id}.json").is_file()
            if transcript_exists:
                status, error = STATUS_COMPLETED, ""
            elif status in (STATUS_PENDING, STATUS_NORMALIZING, STATUS_TRANSCRIBING) and raw_path.is_file():
                status, error = STATUS_PENDING, ""
            elif status != STATUS_FAILED and not raw_path.is_file():
                status, error = STATUS_FAILED, "raw wav missing"
            self._items.append(
                QueueItem(visitor_id=visitor_id, raw_audio_path=raw_path, status=status, error=str(error))
            )
            known_ids.add(visitor_id)

        for raw_path in sorted((root / "audio").glob("visitor_*.wav")):
            visitor_id = raw_path.stem
            if visitor_id not in known_ids:
                status = STATUS_COMPLETED if (transcripts_dir / f"{visitor_id}.json").is_file() else STATUS_PENDING
                self._items.append(QueueItem(visitor_id=visitor_id, raw_audio_path=raw_path, status=status))
        self._persist_locked()

    def _persist_locked(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "queue_version": "1.0",
            "items": [
                {
                    "visitor_id": item.visitor_id,
                    "raw_audio_file": item.raw_audio_path.name,
                    "status": item.status,
                    "error": item.error,
                }
                for item in self._items
            ],
        }
        temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self._state_path)
