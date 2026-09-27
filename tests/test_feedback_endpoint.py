from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from src.operator_server import build_server


class FeedbackApplication:
    def __init__(self, root: Path) -> None:
        self.data_root = root

    def status_snapshot(self) -> dict:
        return {"capture_state": "idle", "report_ready": False}


def _request_feedback(root: Path) -> tuple[int, dict]:
    app = FeedbackApplication(root)
    server = build_server(
        application=app,
        report_generator=lambda _root: {},
        feedback_catalog=[
            {"project_id": "ai_museum", "official_name": "AI Museum"},
            {"project_id": "vision_assist", "official_name": "Vision Assist"},
        ],
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/feedback"
        with urllib.request.urlopen(url) as response:
            return response.status, json.loads(response.read())
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _write_transcript(root: Path, visitor_id: str, text: str) -> None:
    (root / "transcripts").mkdir(parents=True, exist_ok=True)
    (root / "transcripts" / f"{visitor_id}.json").write_text(
        json.dumps({"visitor_id": visitor_id, "text": text, "segments": []}),
        encoding="utf-8",
    )


def _write_classification(root: Path, visitor_id: str, project_ids: list[str]) -> None:
    (root / "classifications").mkdir(parents=True, exist_ok=True)
    (root / "classifications" / f"{visitor_id}.json").write_text(
        json.dumps({"visitor_id": visitor_id, "status": "completed", "project_ids": project_ids, "error": None}),
        encoding="utf-8",
    )


def test_feedback_endpoint_joins_one_transcript_to_multiple_projects(tmp_path: Path):
    _write_transcript(tmp_path, "visitor_0001", "AI Museum and Vision Assist were clear.")
    _write_classification(tmp_path, "visitor_0001", ["ai_museum", "vision_assist"])

    status, body = _request_feedback(tmp_path)

    assert status == 200
    item = body["data"]["items"][0]
    assert [project["project_id"] for project in item["projects"]] == ["ai_museum", "vision_assist"]
    assert item["classification"]["status"] == "completed"


def test_feedback_endpoint_keeps_transcript_pending_without_classification(tmp_path: Path):
    _write_transcript(tmp_path, "visitor_0001", "The visitor was not specific.")

    status, body = _request_feedback(tmp_path)

    assert status == 200
    assert body["data"]["items"][0]["classification"]["status"] == "pending"
    assert body["data"]["items"][0]["projects"] == []


def test_feedback_endpoint_hides_unknown_project_ids(tmp_path: Path):
    _write_transcript(tmp_path, "visitor_0001", "Unknown project.")
    _write_classification(tmp_path, "visitor_0001", ["does_not_exist"])

    status, body = _request_feedback(tmp_path)

    assert status == 200
    item = body["data"]["items"][0]
    assert item["projects"] == []
    assert item["classification"]["status"] == "failed"


def test_feedback_endpoint_handles_malformed_project_ids(tmp_path: Path):
    _write_transcript(tmp_path, "visitor_0001", "Malformed artifact.")
    (tmp_path / "classifications").mkdir(parents=True, exist_ok=True)
    (tmp_path / "classifications" / "visitor_0001.json").write_text(
        json.dumps({"visitor_id": "visitor_0001", "status": "completed", "project_ids": [{}]}),
        encoding="utf-8",
    )

    status, body = _request_feedback(tmp_path)

    assert status == 200
    item = body["data"]["items"][0]
    assert item["projects"] == []
    assert item["classification"]["status"] == "failed"
