"""Single sequential worker — STT-adapter-agnostic.

Normalize -> transcribe -> save transcript. One item at a time.
Failures are isolated per item; the raw accepted WAV is never deleted by the worker.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..audio.normalize import normalize_visitor_recording
from ..pipeline.queue import (
    ProcessingQueue,
    QueueItem,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_NORMALIZING,
    STATUS_PENDING,
    STATUS_TRANSCRIBING,
)
from ..stt.types import TranscriptionAdapter, TranscriptionResult


@dataclass
class WorkerPaths:
    normalized_dir: Path
    quality_dir: Path
    transcripts_dir: Path


def _has_usable_text(result: TranscriptionResult) -> bool:
    return bool(result.text and result.text.strip())


class ProcessingWorker:
    def __init__(
        self,
        *,
        queue: ProcessingQueue,
        adapter: TranscriptionAdapter,
        paths: WorkerPaths,
        target_sample_rate: int,
        target_peak_dbfs: float,
        stt_model: str = "saaras:v3",
        stt_mode: str = "codemix",
        stt_language_code: str = "unknown",
        initial_prompt: str = "",
        on_transcript_ready: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self._queue = queue
        self._adapter = adapter
        self._paths = paths
        self._target_sr = target_sample_rate
        self._target_peak = target_peak_dbfs
        self._stt_model = stt_model
        self._stt_mode = stt_mode
        self._stt_language_code = stt_language_code
        self._initial_prompt = initial_prompt
        self._on_transcript_ready = on_transcript_ready
        self._thread: Optional[threading.Thread] = None
        self._wake = threading.Event()
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="processing-worker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=30.0)
            self._thread = None

    def nudge(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            item = self._queue.pop_pending()
            if item is None:
                self._wake.wait(timeout=0.5)
                self._wake.clear()
                continue
            self._process_one(item)

    def _process_one(self, item: QueueItem) -> None:
        vid = item.visitor_id
        try:
            self._queue.set_status(vid, STATUS_NORMALIZING)
            normalized_path = self._paths.normalized_dir / f"{vid}.wav"
            quality_path = self._paths.quality_dir / f"{vid}.json"
            report = normalize_visitor_recording(
                visitor_id=vid,
                raw_path=item.raw_audio_path,
                normalized_path=normalized_path,
                quality_path=quality_path,
                target_sample_rate=self._target_sr,
                target_peak_dbfs=self._target_peak,
            )
            if report.status not in ("valid",):
                self._queue.set_status(
                    vid, STATUS_FAILED, error=f"normalization status={report.status}"
                )
                return

            self._queue.set_status(vid, STATUS_TRANSCRIBING)
            result: TranscriptionResult = self._adapter.transcribe(
                normalized_path, initial_prompt=self._initial_prompt
            )
            if not _has_usable_text(result):
                self._queue.set_status(vid, STATUS_FAILED, error="transcription returned no text")
                return
            self._save_transcript(vid, item, normalized_path, result)
            self._queue.set_status(vid, STATUS_COMPLETED)
        except Exception as e:
            self._queue.set_status(vid, STATUS_FAILED, error=str(e))

    def _save_transcript(
        self,
        vid: str,
        item: QueueItem,
        normalized_path: Path,
        result: TranscriptionResult,
    ) -> None:
        payload = {
            "visitor_id": vid,
            "raw_audio_file": str(
                Path("..") / "audio" / f"{vid}.wav"
            ),
            "normalized_audio_file": str(
                Path("..") / "normalized" / f"{vid}.wav"
            ),
            "stt_provider": "sarvam",
            "stt_model": self._stt_model,
            "stt_mode": self._stt_mode,
            "stt_language_code": self._stt_language_code,
            "language": result.language,
            "duration_seconds": self._read_duration(normalized_path),
            "text": result.text,
            "segments": [s.__dict__ for s in result.segments],
            "status": "completed",
        }
        out = self._paths.transcripts_dir / f"{vid}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        temporary = out.with_suffix(out.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(out)
        if self._on_transcript_ready is not None:
            try:
                self._on_transcript_ready(out)
            except Exception:
                pass

    @staticmethod
    def _read_duration(wav_path: Path) -> float:
        try:
            import soundfile as sf

            with sf.SoundFile(str(wav_path), mode="r") as f:
                if f.samplerate:
                    return round(f.frames / float(f.samplerate), 3)
        except Exception:
            pass
        return 0.0
