"""State machine tests for the capture + queue pipeline.

These tests use a FakeAdapter (no model load, no mic, no GPU).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pytest
import soundfile as sf

from src.audio.normalize import normalize_visitor_recording
from src.models.transcribe import (
    CudaUnavailableError,
    ModelMissingError,
    TranscriptionAdapter,
    TranscriptionResult,
    Segment,
)
from src.pipeline.queue import (
    ProcessingQueue,
    QueueItem,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_NORMALIZING,
    STATUS_PENDING,
    STATUS_TRANSCRIBING,
)
from src.pipeline.worker import ProcessingWorker, WorkerPaths
from src.storage.session import (
    SessionPaths,
    VisitorIdAllocator,
    new_session_paths,
)


# ---- queue invariants ---------------------------------------------------


def test_queue_status_transitions():
    q = ProcessingQueue()
    q.enqueue(QueueItem(visitor_id="visitor_0001", raw_audio_path=Path("a.wav")))
    assert q.has_pending()
    assert q.pop_pending() is not None
    q.set_status("visitor_0001", STATUS_NORMALIZING)
    assert not q.has_pending()
    assert q.has_in_flight()
    q.set_status("visitor_0001", STATUS_TRANSCRIBING)
    q.set_status("visitor_0001", STATUS_COMPLETED)
    assert not q.has_open_work()
    assert q.counts()[STATUS_COMPLETED] == 1


def test_queue_enqueue_rejects_non_pending():
    q = ProcessingQueue()
    item = QueueItem(visitor_id="visitor_0001", raw_audio_path=Path("a.wav"))
    item.status = STATUS_NORMALIZING
    with pytest.raises(ValueError):
        q.enqueue(item)


# ---- worker with fake adapter ------------------------------------------


def _write_wav(path: Path, seconds: float = 1.0, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, seconds, int(seconds * sr), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    sf.write(str(path), samples, sr, subtype="PCM_16")


def test_worker_processes_one_at_a_time(tmp_path):
    from tests.conftest import FakeAdapter

    sessions_root = tmp_path
    paths: SessionPaths = new_session_paths(sessions_root)
    for i in range(1, 4):
        _write_wav(paths.audio / f"visitor_000{i}.wav", seconds=0.6)

    q = ProcessingQueue()
    for i in range(1, 4):
        q.enqueue(
            QueueItem(
                visitor_id=f"visitor_000{i}",
                raw_audio_path=paths.audio / f"visitor_000{i}.wav",
            )
        )
    adapter = FakeAdapter()
    worker = ProcessingWorker(
        queue=q,
        adapter=adapter,
        paths=WorkerPaths(
            normalized_dir=paths.normalized,
            quality_dir=paths.quality,
            transcripts_dir=paths.transcripts,
        ),
        target_sample_rate=16000,
        target_peak_dbfs=-3.0,
        model_name="Systran/faster-whisper-small",
        device="cuda",
        compute_type="float16",
    )
    # Do NOT call worker.start(): the test calls _process_one directly in the
    # main thread to assert deterministic FIFO ordering.
    for _ in range(3):
        item = q.pop_pending()
        if item is None:
            break
        worker._process_one(item)  # noqa: SLF001 - test-only entry point
    worker.stop()
    counts = q.counts()
    assert counts[STATUS_COMPLETED] == 3
    assert counts[STATUS_FAILED] == 0
    assert len(adapter.calls) == 3
    # The adapter must be called one at a time - the worker has a single thread.
    # Order must match FIFO.
    seen = [p.stem for p in adapter.calls]
    assert seen == ["visitor_0001", "visitor_0002", "visitor_0003"]


def test_worker_failure_preserves_raw_wav(tmp_path):
    from tests.conftest import FakeAdapter

    paths = new_session_paths(tmp_path)
    raw = paths.audio / "visitor_0001.wav"
    _write_wav(raw, seconds=0.5)
    before_bytes = raw.read_bytes()

    q = ProcessingQueue()
    q.enqueue(QueueItem(visitor_id="visitor_0001", raw_audio_path=raw))
    adapter = FakeAdapter(fail_on={"visitor_0001"})
    worker = ProcessingWorker(
        queue=q,
        adapter=adapter,
        paths=WorkerPaths(
            normalized_dir=paths.normalized,
            quality_dir=paths.quality,
            transcripts_dir=paths.transcripts,
        ),
        target_sample_rate=16000,
        target_peak_dbfs=-3.0,
        model_name="Systran/faster-whisper-small",
        device="cuda",
        compute_type="float16",
    )
    item = q.pop_pending()
    worker._process_one(item)  # noqa: SLF001
    worker.stop()

    assert q.counts()[STATUS_FAILED] == 1
    assert raw.exists(), "raw wav must be preserved on failure"
    assert raw.read_bytes() == before_bytes
    # Worker does not write a transcript on failure.
    assert not (paths.transcripts / "visitor_0001.json").exists()


# ---- allocator invariants (mirror ENTER/ESC/Q rules) -------------------


def test_allocator_advances_on_accept_only():
    a = VisitorIdAllocator()
    assert a.current() == "visitor_0001"
    accepted = a.allocate()
    assert accepted == "visitor_0001"
    assert a.current() == "visitor_0002"


def test_allocator_retry_does_not_increment():
    """ESC keeps the same visitor number; only ENTER advances."""
    a = VisitorIdAllocator()
    a.allocate()  # first accept
    # ESC path: do NOT call allocate; current stays the same.
    assert a.current() == "visitor_0002"


# ---- normalize isolated behavior --------------------------------------


def test_normalize_preserves_raw_and_writes_separate_outputs(tmp_path):
    raw = tmp_path / "raw.wav"
    _write_wav(raw, seconds=0.5, sr=22050)
    before = raw.read_bytes()
    norm = tmp_path / "norm.wav"
    qual = tmp_path / "q.json"
    report = normalize_visitor_recording(
        visitor_id="visitor_0001",
        raw_path=raw,
        normalized_path=norm,
        quality_path=qual,
        target_sample_rate=16000,
        target_peak_dbfs=-3.0,
    )
    assert report.status == "valid"
    assert raw.read_bytes() == before
    assert norm.exists()
    assert qual.exists()
    info = sf.info(str(norm))
    assert info.samplerate == 16000
    assert info.channels == 1
