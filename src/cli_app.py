"""Main CLI: lifecycle, threads, status render, safe Stop Capture behaviour."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .agent.feedback_agent import FeedbackAgentWorker
from .audio.capture import CaptureSession
from .config import Config, load_config
from .controls.keyboard import KeyboardListener
from .pipeline.queue import ProcessingQueue, QueueItem
from .pipeline.worker_v2 import ProcessingWorker, WorkerPaths
from .reporting.event_report import has_unreported_transcripts
from .storage.data import DataPaths, VisitorIdAllocator, data_paths, next_visitor_number
from .stt.errors import SarvamApiKeyMissingError
from .stt.factory import build_default_adapter
from .stt.types import TranscriptionAdapter

load_dotenv(override=False)


class Application:
    def __init__(self, config: Config, adapter: TranscriptionAdapter) -> None:
        self._config = config
        self._adapter = adapter
        self._queue = ProcessingQueue()
        self._allocator = VisitorIdAllocator()
        self._stop_capture = threading.Event()
        self._shutting_down = threading.Event()
        self._capture: Optional[CaptureSession] = None
        self._keyboard: Optional[KeyboardListener] = None
        self._worker: Optional[ProcessingWorker] = None
        self._agent_worker: Optional[FeedbackAgentWorker] = None
        self._paths: Optional[DataPaths] = None
        self._action_lock = threading.Lock()

    # ---- public lifecycle ---------------------------------------------

    def run(self) -> int:
        self.start()
        self._start_keyboard()
        try:
            self._render_loop()
        finally:
            self.close()
        return 0

    def start(self, *, start_capture: bool = True) -> None:
        """Open global storage and worker, optionally beginning the first recording."""
        if self._paths is not None:
            raise RuntimeError("Application is already started")
        self._paths = data_paths(self._config.data_root)
        self._queue = ProcessingQueue(state_path=self._paths.queue)
        self._allocator.reset(next_visitor_number(self._paths.audio))
        self._start_worker()

        if start_capture:
            self._start_capture_for_current()

    def start_capture(self) -> dict:
        with self._action_lock:
            if self._paths is None:
                raise RuntimeError("Application is not started")
            if self._stop_capture.is_set():
                raise RuntimeError("Capture is already stopped")
            if self._capture is not None and self._capture.is_running:
                raise RuntimeError("A visitor recording is already active")
            self._start_capture_for_current()
            return self.status_snapshot()

    def accept_current(self) -> dict:
        with self._action_lock:
            self._require_recording()
            self._handle_accept(start_next=True)
            return self.status_snapshot()

    def accept_and_pause(self) -> dict:
        with self._action_lock:
            self._require_recording()
            self._handle_accept(start_next=False)
            return self.status_snapshot()

    def discard_current(self) -> dict:
        with self._action_lock:
            self._require_recording()
            self._handle_discard()
            return self.status_snapshot()

    def stop_capture(self) -> dict:
        with self._action_lock:
            if self._paths is None:
                raise RuntimeError("Application is not started")
            if self._stop_capture.is_set():
                raise RuntimeError("Capture is already stopped")
            self._handle_stop_capture()
            return self.status_snapshot()

    def status_snapshot(self) -> dict:
        capture = self._capture
        recording = bool(capture and capture.is_running)
        counts = self._queue.counts()
        return {
            "capture_state": "recording" if recording else "stopped" if self._stop_capture.is_set() else "idle",
            "current_visitor_id": capture.current_visitor if recording else None,
            "elapsed_seconds": capture.elapsed_seconds if recording else 0,
            "input_level": round(capture.input_level, 4) if recording else 0.0,
            "queue": {
                "counts": counts,
                "items": [
                    {"visitor_id": item.visitor_id, "status": item.status, "error": item.error}
                    for item in self._queue.items()
                ],
            },
            "report_ready": bool(
                self._paths
                and not recording
                and not self._queue.has_open_work()
                and has_unreported_transcripts(self._paths.root)
            ),
        }

    @property
    def data_root(self) -> Optional[Path]:
        return self._paths.root if self._paths else None

    def close(self) -> None:
        self._shutdown()

    def _require_recording(self) -> None:
        if self._paths is None:
            raise RuntimeError("Application is not started")
        if self._capture is None or not self._capture.is_running:
            raise RuntimeError("No visitor recording is active")

    # ---- workers -------------------------------------------------------

    def _start_keyboard(self) -> None:
        self._keyboard = KeyboardListener(on_action=self._on_key_action)
        self._keyboard.start()

    def _start_worker(self) -> None:
        assert self._paths is not None
        agent_enqueue = None
        try:
            catalog_path = Path(__file__).resolve().parents[1] / "context" / "project_catalog.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8")).get("projects", [])
            self._agent_worker = FeedbackAgentWorker(
                transcripts_dir=self._paths.transcripts,
                classifications_dir=self._paths.classifications,
                catalog=catalog,
                api_key=self._config.sarvam_api_key,
            )
            self._agent_worker.start()
            agent_enqueue = self._agent_worker.enqueue
        except Exception as error:
            self._agent_worker = None
            print(f"[agent] disabled: {error}", flush=True)
        paths = WorkerPaths(
            normalized_dir=self._paths.normalized,
            quality_dir=self._paths.quality,
            transcripts_dir=self._paths.transcripts,
        )
        self._worker = ProcessingWorker(
            queue=self._queue,
            adapter=self._adapter,
            paths=paths,
            target_sample_rate=self._config.target_sample_rate,
            target_peak_dbfs=self._config.peak_target_dbfs,
            stt_model=self._config.sarvam_model,
            stt_mode=self._config.sarvam_mode,
            stt_language_code=self._config.sarvam_language_code,
            on_transcript_ready=agent_enqueue,
        )
        self._worker.start()

    def _start_capture_for_current(self) -> None:
        if self._shutting_down.is_set():
            return
        assert self._paths is not None
        self._capture = CaptureSession(
            input_device=self._config.input_device,
            preferred_sample_rate=self._config.target_sample_rate,
            channels=self._config.channels,
            block_size=self._config.block_size,
            queue_max_blocks=self._config.audio_queue_blocks,
            audio_dir=self._paths.audio,
            peak_target_dbfs=self._config.peak_target_dbfs,
        )
        visitor_id = self._allocator.current()
        self._capture.start(visitor_id)
        print(f"[capture] recording {visitor_id}", flush=True)

    # ---- keyboard actions ---------------------------------------------

    def _on_key_action(self, action: str) -> None:
        if self._shutting_down.is_set():
            return
        try:
            if action == "accept":
                self.accept_current()
            elif action == "discard":
                self.discard_current()
            elif action == "stop":
                self.stop_capture()
        except RuntimeError:
            return

    def _handle_accept(self, *, start_next: bool) -> None:
        if self._capture is None or not self._capture.is_running:
            return
        result = self._capture.finalize_and_accept()
        if not result.ok:
            print(
                f"[capture] accept failed (empty/invalid): {result.path}",
                flush=True,
            )
            try:
                result.path.unlink(missing_ok=True)
            except OSError:
                pass
            if start_next:
                self._start_capture_for_current()
            return

        visitor_id = self._allocator.current()
        permanent = result.path.parent / f"{visitor_id}.wav"
        if permanent.exists():
            print(
                f"[capture] refusing to overwrite existing {permanent.name}",
                flush=True,
            )
            return
        os.replace(result.path, permanent)
        self._queue.enqueue(
            QueueItem(visitor_id=visitor_id, raw_audio_path=permanent)
        )
        self._allocator.allocate()
        if self._worker is not None:
            self._worker.nudge()
        print(f"[capture] accepted {visitor_id} -> queue", flush=True)
        if start_next:
            self._start_capture_for_current()

    def _handle_discard(self) -> None:
        if self._capture is None or not self._capture.is_running:
            return
        result = self._capture.finalize_and_discard()
        if result.error:
            print(f"[capture] discard error: {result.error}", flush=True)
        else:
            print("[capture] discarded current partial", flush=True)
        self._start_capture_for_current()

    def _handle_stop_capture(self) -> None:
        if self._stop_capture.is_set():
            return
        self._stop_capture.set()
        if self._capture is not None and self._capture.is_running:
            result = self._capture.finalize_and_discard()
            if result.error:
                print(f"[stop] partial delete error: {result.error}", flush=True)
        print("[stop] capture halted; draining accepted queue", flush=True)

    # ---- status render loop -------------------------------------------

    def _render_loop(self) -> None:
        try:
            while True:
                self._render_status()
                if self._stop_capture.is_set() and not self._queue.has_open_work():
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            self._handle_stop_capture()

    def _render_status(self) -> None:
        if self._shutting_down.is_set():
            return
        sys.stdout.write("\x1b[H\x1b[J")
        self._print_banner()
        counts = self._queue.counts()
        processing = self._queue.current_processing()
        waiting = counts["pending"]
        completed = counts["completed"]
        failed = counts["failed"]
        if self._capture is not None and self._capture.is_running:
            print(f"RECORDING: {self._capture.current_visitor}")
        elif self._stop_capture.is_set():
            print("CAPTURE: stopped (draining queue)")
        else:
            print("CAPTURE: idle")
        print(
            f"Processing now: {processing.visitor_id if processing else '-'}\n"
            f"Waiting in queue: {waiting}\n"
            f"Completed: {completed}\n"
            f"Failed: {failed}\n"
        )
        failed_items = self._queue.failed_items()
        if failed_items:
            print("Recent failures:")
            for it in failed_items[-3:]:
                reason = it.error or "unknown"
                print(f"  {it.visitor_id}: {reason}")
            print()
        print("ENTER  Accept current visitor")
        print("ESC    Discard and retry current visitor")
        print("Q      Stop capture safely")
        sys.stdout.flush()

    def _print_banner(self) -> None:
        print("=== FEEDBACK CAPTURE SYSTEM ===")
        if self._paths is not None:
            print(f"Data: {self._paths.root}")
        print()

    # ---- shutdown ------------------------------------------------------

    def _shutdown(self) -> None:
        self._shutting_down.set()
        if self._keyboard is not None:
            self._keyboard.stop()
        if self._worker is not None:
            self._worker.stop()
        if self._agent_worker is not None:
            self._agent_worker.stop()
        if self._capture is not None and self._capture.is_running:
            try:
                result = self._capture.finalize_and_discard()
                if result.error:
                    print(f"[shutdown] partial error: {result.error}", flush=True)
            except Exception:
                pass
        print("[shutdown] complete", flush=True)


# ---- entry point ---------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="event-lens")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML config file. Default: ./config.toml",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override [storage].data_root from config.",
    )
    p.add_argument("--input-device", type=int, default=None)
    p.add_argument(
        "--check-only",
        action="store_true",
        help="Validate configuration, then exit.",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    cli_overrides: dict = {}
    if args.data_root is not None:
        cli_overrides["data_root"] = args.data_root
    if args.input_device is not None:
        cli_overrides["input_device"] = args.input_device

    config = load_config(config_path=args.config, cli_overrides=cli_overrides)
    try:
        adapter = build_default_adapter(
            api_key=config.sarvam_api_key,
            model=config.sarvam_model,
            mode=config.sarvam_mode,
            language_code=config.sarvam_language_code,
        )
    except SarvamApiKeyMissingError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.check_only:
        print(f"[check] stt_provider = sarvam")
        print(f"[check] stt_model    = {config.sarvam_model}")
        print(f"[check] stt_mode     = {config.sarvam_mode}")
        print("[check] configuration OK")
        return 0

    app = Application(config=config, adapter=adapter)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
