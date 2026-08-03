"""Main CLI: lifecycle, threads, status render, safe Stop Capture behaviour."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .audio.capture import CaptureSession
from .config import Config, load_config
from .controls.keyboard import KeyboardListener
from .pipeline.queue import (
    ProcessingQueue,
    QueueItem,
    STATUS_PENDING,
)
from .pipeline.worker_v2 import ProcessingWorker, WorkerPaths
from .storage.session import (
    SessionPaths,
    VisitorIdAllocator,
    new_session_paths,
    write_session_json,
)
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
        self._paths: Optional[SessionPaths] = None
        self._started_at: Optional[datetime] = None

    # ---- public lifecycle ---------------------------------------------

    def run(self) -> int:
        self._paths = new_session_paths(self._config.sessions_root)
        self._started_at = datetime.now()
        write_session_json(self._paths, self._started_at)
        self._allocator.reset()

        self._print_banner()
        self._start_capture_for_current()
        self._start_keyboard()
        self._start_worker()

        try:
            self._render_loop()
        finally:
            self._shutdown()

        return 0

    # ---- workers -------------------------------------------------------

    def _start_keyboard(self) -> None:
        self._keyboard = KeyboardListener(on_action=self._on_key_action)
        self._keyboard.start()

    def _start_worker(self) -> None:
        assert self._paths is not None
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
            sessions_audio_dir=self._paths.audio,
            peak_target_dbfs=self._config.peak_target_dbfs,
        )
        visitor_id = self._allocator.current()
        self._capture.start(visitor_id)
        print(f"[capture] recording {visitor_id}", flush=True)

    # ---- keyboard actions ---------------------------------------------

    def _on_key_action(self, action: str) -> None:
        if self._shutting_down.is_set():
            return
        if action == "accept":
            self._handle_accept()
        elif action == "discard":
            self._handle_discard()
        elif action == "stop":
            self._handle_stop_capture()

    def _handle_accept(self) -> None:
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
            self._start_capture_for_current()
            return

        visitor_id = self._allocator.current()
        permanent = self._capture._sessions_audio_dir / f"{visitor_id}.wav"
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
            print(f"Session: {self._paths.root.name}")
        print()

    # ---- shutdown ------------------------------------------------------

    def _shutdown(self) -> None:
        self._shutting_down.set()
        if self._keyboard is not None:
            self._keyboard.stop()
        if self._worker is not None:
            self._worker.stop()
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
    p = argparse.ArgumentParser(prog="feedback-llm")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to TOML config file. Default: ./config.toml",
    )
    p.add_argument(
        "--sessions-root",
        type=Path,
        default=None,
        help="Override [sessions].sessions_root from config.",
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
    if args.sessions_root is not None:
        cli_overrides["sessions_root"] = args.sessions_root
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
