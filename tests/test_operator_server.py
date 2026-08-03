from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from src.audio.capture import CaptureSession
from src.operator_server import build_server


class FakeApplication:
    def __init__(self, root: Path) -> None:
        self.data_root = root
        self.recording = False
        self.stopped = False

    def status_snapshot(self) -> dict:
        return {
            "capture_state": "recording" if self.recording else "stopped" if self.stopped else "idle",
            "current_visitor_id": "visitor_0001" if self.recording else None,
            "elapsed_seconds": 2,
            "input_level": 0.2,
            "queue": {"counts": {}, "items": []},
            "report_ready": self.stopped and not self.recording,
        }

    def start_capture(self) -> dict:
        if self.stopped:
            raise RuntimeError("Capture is already stopped")
        if self.recording:
            raise RuntimeError("A visitor recording is already active")
        self.recording = True
        return self.status_snapshot()

    def accept_current(self) -> dict:
        if not self.recording:
            raise RuntimeError("No visitor recording is active")
        return self.status_snapshot()

    def accept_and_pause(self) -> dict:
        if not self.recording:
            raise RuntimeError("No visitor recording is active")
        self.recording = False
        return self.status_snapshot()

    def discard_current(self) -> dict:
        return self.accept_current()

    def stop_capture(self) -> dict:
        self.recording = False
        self.stopped = True
        return self.status_snapshot()


def _request(url: str, method: str = "GET") -> tuple[int, dict]:
    request = urllib.request.Request(url, data=b"{}" if method == "POST" else None, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_local_api_returns_status_and_rejects_invalid_transition(tmp_path: Path):
    app = FakeApplication(tmp_path)
    server = build_server(application=app, report_generator=lambda root: {"markdown_url": "/api/report/markdown"}, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _request(f"{base_url}/api/status")
        assert status == 200
        assert body["data"]["capture_state"] == "idle"

        status, body = _request(f"{base_url}/api/capture/start", "POST")
        assert status == 200
        assert body["data"]["current_visitor_id"] == "visitor_0001"

        status, body = _request(f"{base_url}/api/capture/accept-and-pause", "POST")
        assert status == 200
        assert body["data"]["capture_state"] == "idle"

        status, body = _request(f"{base_url}/api/capture/start", "POST")
        assert status == 200
        assert body["data"]["capture_state"] == "recording"

        status, body = _request(f"{base_url}/api/capture/stop", "POST")
        assert status == 200
        assert body["data"]["capture_state"] == "stopped"

        status, body = _request(f"{base_url}/api/capture/accept", "POST")
        assert status == 409
        assert body["error"]["code"] == "invalid_capture_state"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_capture_exposes_real_input_level(tmp_path: Path):
    capture = CaptureSession(
        input_device=None,
        preferred_sample_rate=16_000,
        channels=1,
        block_size=4000,
        queue_max_blocks=2,
        audio_dir=tmp_path,
        peak_target_dbfs=-3.0,
    )
    capture._on_audio(np.array([[0.5], [-0.5]], dtype=np.float32), 2, None, None)  # noqa: SLF001
    assert capture.input_level == 0.5
