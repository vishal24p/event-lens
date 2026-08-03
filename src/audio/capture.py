"""Operator-controlled microphone capture.

The PortAudio callback only:
  1. checks the stream status,
  2. copies the incoming audio block,
  3. puts it on a bounded queue,
  4. returns.

A dedicated writer thread owns the active `SoundFile` handle. ENTER, ESC, and Q
request the writer to stop, finalize, and ACK. Only then is the partial file
renamed or deleted.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


# Sentinel types used over the audio queue and command queue.
@dataclass
class _Stop:
    pass


@dataclass
class _FinalizeResult:
    path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    ok: bool
    error: str = ""


class CaptureSession:
    """Owns one microphone recording lifecycle.

    Public surface:
        start(visitor_id) -> opens partial WAV, begins writing
        finalize_and_accept() -> stop, close, return path ready for rename
        finalize_and_discard() -> stop, close, delete partial file
        stop_only() -> stop, close, do not delete (caller deletes via result)
    """

    def __init__(
        self,
        *,
        input_device: Optional[int],
        preferred_sample_rate: int,
        channels: int,
        block_size: int,
        queue_max_blocks: int,
        audio_dir: Path,
        peak_target_dbfs: float,
    ) -> None:
        self._input_device = input_device
        self._preferred_sr = preferred_sample_rate
        self._channels = channels
        self._block_size = block_size
        self._audio_q: "queue.Queue[np.ndarray | _Stop]" = queue.Queue(
            maxsize=queue_max_blocks
        )
        self._audio_dir = audio_dir
        self._peak_target_dbfs = peak_target_dbfs

        self._writer_thread: Optional[threading.Thread] = None
        self._stream: Optional[sd.InputStream] = None
        self._current_path: Optional[Path] = None
        self._current_visitor: Optional[str] = None
        self._lock = threading.Lock()
        self._is_running = False
        self._input_level = 0.0
        self._started_at: Optional[float] = None

    # ---- lifecycle -----------------------------------------------------

    def start(self, visitor_id: str) -> Path:
        with self._lock:
            if self._is_running:
                raise RuntimeError("CaptureSession already running")
            self._audio_dir.mkdir(parents=True, exist_ok=True)
            partial = self._audio_dir / f"{visitor_id}.partial.wav"
            if partial.exists():
                # Defensive: stale partial from a crash. Discard before opening.
                partial.unlink()

            sample_rate = self._open_stream()
            self._current_path = partial
            self._current_visitor = visitor_id
            self._started_at = time.monotonic()
            self._writer_thread = threading.Thread(
                target=self._writer_loop,
                name=f"writer-{visitor_id}",
                daemon=True,
            )
            self._writer_thread.start()
            self._is_running = True
            return partial

    def finalize_and_accept(self) -> _FinalizeResult:
        """Stop capture, close file, return result. Caller renames the partial."""
        with self._lock:
            if not self._is_running:
                raise RuntimeError("CaptureSession not running")
            return self._finalize_locked(delegate_delete=False)

    def finalize_and_discard(self) -> _FinalizeResult:
        """Stop capture, close file, delete the partial. Returns the path that was deleted."""
        with self._lock:
            if not self._is_running:
                raise RuntimeError("CaptureSession not running")
            return self._finalize_locked(delegate_delete=True)

    # ---- internals -----------------------------------------------------

    def _open_stream(self) -> int:
        device_info = sd.query_devices(device=self._input_device, kind="input")
        # Use the device's native rate if 16 kHz isn't available, capture mono.
        device_sr = int(device_info["default_samplerate"])
        sample_rate = (
            self._preferred_sr
            if self._preferred_sr in (16_000, device_sr)
            else device_sr
        )
        # Store on instance for the writer thread.
        self._sample_rate = sample_rate

        self._stream = sd.InputStream(
            samplerate=sample_rate,
            channels=self._channels,
            dtype="float32",
            blocksize=self._block_size,
            device=self._input_device,
            callback=self._on_audio,
        )
        self._stream.start()
        return sample_rate

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            # Surface overruns/underruns via stderr; do not block the callback.
            print(f"[capture] stream status: {status}", flush=True)
        self._input_level = float(np.sqrt(np.mean(np.square(indata))))
        # Copy out of the PortAudio buffer; the callback must not retain a view.
        block = np.array(indata, copy=True)
        try:
            self._audio_q.put(block, timeout=0.1)
        except queue.Full:
            # Drop oldest by getting then putting to keep the most recent audio.
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._audio_q.put_nowait(block)
            except queue.Full:
                pass

    def _writer_loop(self) -> None:
        assert self._current_path is not None
        assert hasattr(self, "_sample_rate")
        path = self._current_path
        sr = self._sample_rate
        ch = self._channels
        sample_count = 0
        try:
            with sf.SoundFile(
                str(path), mode="w", samplerate=sr, channels=ch, subtype="PCM_16"
            ) as f:
                while True:
                    item = self._audio_q.get()
                    if isinstance(item, _Stop):
                        break
                    f.write(item)
                    sample_count += item.shape[0]
        except Exception as e:  # pragma: no cover - defensive
            print(f"[capture] writer error: {e}", flush=True)

        # Store final stats for the finalize caller.
        self._writer_sample_count = sample_count
        self._writer_sr = sr
        self._writer_ch = ch
        # Signal completion via the queue with a special marker.
        try:
            self._audio_q.put_nowait(_Stop())
        except queue.Full:
            # Drain one then put.
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                pass
            self._audio_q.put_nowait(_Stop())

    def _finalize_locked(self, *, delegate_delete: bool) -> _FinalizeResult:
        # 1. Stop the PortAudio stream so no more callbacks fire.
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:  # pragma: no cover
                print(f"[capture] stream close error: {e}", flush=True)
            self._stream = None

        # 2. Tell the writer to stop and wait for it to finish.
        try:
            self._audio_q.put(_Stop(), timeout=1.0)
        except queue.Full:
            pass
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=10.0)
            self._writer_thread = None

        path = self._current_path
        assert path is not None
        sr = getattr(self, "_writer_sr", 0)
        ch = getattr(self, "_writer_ch", 0)
        sample_count = getattr(self, "_writer_sample_count", 0)
        duration = (sample_count / sr) if sr else 0.0

        ok = path.exists() and path.stat().st_size > 0 and sample_count > 0

        result = _FinalizeResult(
            path=path,
            duration_seconds=duration,
            sample_rate=sr,
            channels=ch,
            ok=ok,
        )

        if delegate_delete and path.exists():
            try:
                path.unlink()
            except OSError as e:  # pragma: no cover
                result.error = f"failed to delete partial: {e}"

        # Reset state for the next visitor.
        self._is_running = False
        self._current_path = None
        self._current_visitor = None
        self._started_at = None
        # Drain the queue so the next recording starts clean.
        try:
            while True:
                self._audio_q.get_nowait()
        except queue.Empty:
            pass
        return result

    # ---- read-only state for the UI ------------------------------------

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def current_visitor(self) -> Optional[str]:
        return self._current_visitor

    @property
    def input_level(self) -> float:
        """Current RMS input level (0.0 to 1.0) for the local operator UI."""
        return self._input_level

    @property
    def elapsed_seconds(self) -> int:
        return int(time.monotonic() - self._started_at) if self._started_at else 0
