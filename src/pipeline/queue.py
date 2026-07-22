"""FIFO queue of accepted recordings waiting for processing."""
from __future__ import annotations

import json
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
    """Thread-safe FIFO with status tracking."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: List[QueueItem] = []

    def enqueue(self, item: QueueItem) -> None:
        with self._lock:
            if item.status != STATUS_PENDING:
                raise ValueError("enqueue requires pending status")
            self._items.append(item)

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
            return any(i.status != STATUS_COMPLETED for i in self._items)

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
