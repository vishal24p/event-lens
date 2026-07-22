"""Worker integration tests with a fake adapter."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.pipeline.queue import (
    ProcessingQueue,
    QueueItem,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
from src.pipeline.worker import ProcessingWorker, WorkerPaths
from src.storage.session import new_session_paths

from tests.conftest import FakeAdapter


def _sine(path: Path, seconds: float = 0.5, sr: int = 16000) -> None:
    t = np.linspace(0, seconds, int(seconds * sr), endpoint=False)
    sf.write(
        str(path),
        (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32),
        sr,
    )


def test_drain_processes_all_accepted(tmp_path):
    paths = new_session_paths(tmp_path)
    for i in range(1, 4):
        _sine(paths.audio / f"visitor_000{i}.wav", seconds=0.4)
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
    worker.start()
    # Drive with nudges until drained.
    import time

    for _ in range(40):
        worker.nudge()
        if not q.has_open_work():
            break
        time.sleep(0.05)
    worker.stop()
    assert q.counts()[STATUS_COMPLETED] == 3


def test_failure_does_not_destroy_queue(tmp_path):
    paths = new_session_paths(tmp_path)
    for i in range(1, 4):
        _sine(paths.audio / f"visitor_000{i}.wav", seconds=0.4)
    q = ProcessingQueue()
    for i in range(1, 4):
        q.enqueue(
            QueueItem(
                visitor_id=f"visitor_000{i}",
                raw_audio_path=paths.audio / f"visitor_000{i}.wav",
            )
        )
    adapter = FakeAdapter(fail_on={"visitor_0002"})
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
    worker.start()
    import time

    for _ in range(60):
        worker.nudge()
        if not q.has_open_work():
            break
        time.sleep(0.05)
    worker.stop()
    counts = q.counts()
    assert counts[STATUS_FAILED] == 1
    assert counts[STATUS_COMPLETED] == 2
    # Raw WAV of the failed one is still on disk.
    assert (paths.audio / "visitor_0002.wav").exists()
