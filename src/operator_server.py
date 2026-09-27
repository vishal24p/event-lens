"""Local browser-control API for the feedback capture application."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional

from .cli_app import Application
from .config import Config, load_config
from .reporting.event_report import EventReportError, generate_event_report
from .stt.errors import SarvamApiKeyMissingError
from .stt.factory import build_default_adapter


class ApiConflict(RuntimeError):
    pass


ReportGenerator = Callable[[Path], dict]


def _project_catalog() -> list[dict]:
    path = _project_root() / "context" / "project_catalog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    projects = payload.get("projects")
    if not isinstance(projects, list):
        raise EventReportError("project catalog has no projects list")
    return [project for project in projects if isinstance(project, dict)]


def _feedback_items(data_root: Path, catalog: list[dict]) -> list[dict]:
    projects = {
        project["project_id"]: project
        for project in catalog
        if isinstance(project.get("project_id"), str) and project["project_id"]
    }
    items = []
    transcripts_dir = data_root / "transcripts"
    classifications_dir = data_root / "classifications"
    for transcript_path in sorted(transcripts_dir.glob("visitor_*.json"), reverse=True):
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EventReportError(f"invalid transcript file {transcript_path.name}: {error}") from error
        visitor_id = transcript.get("visitor_id")
        text = transcript.get("text")
        if not isinstance(visitor_id, str) or not isinstance(text, str) or not text.strip():
            continue

        classification = {"status": "pending", "project_ids": [], "error": None}
        classification_path = classifications_dir / transcript_path.name
        if classification_path.is_file():
            try:
                stored = json.loads(classification_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                stored = {"status": "failed", "project_ids": [], "error": str(error)}
            if isinstance(stored, dict):
                classification.update(
                    status=stored.get("status", "failed"),
                    project_ids=stored.get("project_ids", []),
                    error=stored.get("error"),
                )

        requested_ids = classification["project_ids"]
        if not isinstance(requested_ids, list):
            requested_ids = []
            classification["status"] = "failed"
            classification["error"] = "classification project_ids must be a list"
        invalid_ids = [project_id for project_id in requested_ids if not isinstance(project_id, str)]
        unknown_ids = [project_id for project_id in requested_ids if isinstance(project_id, str) and project_id not in projects]
        if invalid_ids or unknown_ids:
            classification["status"] = "failed"
            classification["error"] = f"invalid project ids: {invalid_ids + unknown_ids}"
        valid_ids = [project_id for project_id in requested_ids if isinstance(project_id, str) and project_id in projects]
        classification["project_ids"] = valid_ids
        resolved_projects = [
            {
                "project_id": project_id,
                "name": projects[project_id].get("short_name")
                or projects[project_id].get("official_name")
                or project_id,
                "zone": projects[project_id].get("zone"),
            }
            for project_id in valid_ids
        ]
        items.append(
            {
                "visitor_id": visitor_id,
                "text": text,
                "segments": transcript.get("segments") if isinstance(transcript.get("segments"), list) else [],
                "classification": classification,
                "projects": resolved_projects,
            }
        )
    return items


def build_server(
    *,
    application: Application,
    report_generator: ReportGenerator,
    feedback_catalog: Optional[list[dict]] = None,
    port: int = 8765,
) -> ThreadingHTTPServer:
    catalog = feedback_catalog

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # pragma: no cover - noisy server default
            return

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, code: str, message: str) -> None:
            self._json(status, {"error": {"code": code, "message": message}})

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/api/status":
                self._json(200, {"data": application.status_snapshot()})
                return
            if self.path == "/api/feedback":
                data_root = application.data_root
                if data_root is None:
                    self._error(409, "feedback_unavailable", "The feedback pipeline is not running.")
                    return
                try:
                    resolved_catalog = catalog if catalog is not None else _project_catalog()
                    self._json(200, {"data": {"items": _feedback_items(data_root, resolved_catalog)}})
                except (EventReportError, OSError, json.JSONDecodeError) as error:
                    self._error(500, "feedback_unavailable", str(error))
                return
            if self.path == "/api/report/markdown":
                data_root = application.data_root
                path = data_root / "reports" / "event_feedback_report.md" if data_root else None
                if path is None or not path.is_file():
                    self._error(404, "report_not_found", "No event feedback report has been generated yet.")
                    return
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._error(404, "not_found", "Unknown endpoint.")

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            actions = {
                "/api/capture/start": application.start_capture,
                "/api/capture/accept": application.accept_current,
                "/api/capture/accept-and-pause": application.accept_and_pause,
                "/api/capture/discard": application.discard_current,
                "/api/capture/stop": application.stop_capture,
            }
            if self.path in actions:
                try:
                    status = actions[self.path]()
                except RuntimeError as error:
                    self._error(409, "invalid_capture_state", str(error))
                    return
                self._json(200, {"data": status})
                return
            if self.path == "/api/report":
                try:
                    status = application.status_snapshot()
                    if not status["report_ready"]:
                        raise ApiConflict("Stop capture and wait for all accepted recordings to finish transcribing first.")
                    data_root = application.data_root
                    if data_root is None:
                        raise ApiConflict("The feedback pipeline is not running.")
                    self._json(200, {"data": report_generator(data_root)})
                except (ApiConflict, EventReportError) as error:
                    self._error(409, "report_not_ready", str(error))
                except Exception:  # pragma: no cover - provider/network failure boundary
                    self._error(500, "report_failed", "The event feedback report could not be generated.")
                return
            self._error(404, "not_found", "Unknown endpoint.")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _report_generator(config: Config) -> ReportGenerator:
    root = _project_root()
    catalog_path = root / "context" / "project_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    prompt = (root / "prompts" / "event_feedback_report_v1.txt").read_text(encoding="utf-8")
    schema = json.loads((root / "schemas" / "event_feedback_report_v1.json").read_text(encoding="utf-8"))
    model = os.environ.get("SARVAM_LLM_MODEL", "sarvam-105b")

    def generate(data_root: Path) -> dict:
        outcome = generate_event_report(
            data_root=data_root,
            catalog=catalog,
            system_prompt=prompt,
            response_schema=schema,
            api_key=config.sarvam_api_key,
            model=model,
        )
        return {"markdown_url": "/api/report/markdown", "model": outcome.actual_model}

    return generate


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m src.operator_server")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--input-device", type=int)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    overrides = {key: value for key, value in {"data_root": args.data_root, "input_device": args.input_device}.items() if value is not None}
    config = load_config(config_path=args.config, cli_overrides=overrides)
    try:
        adapter = build_default_adapter(
            api_key=config.sarvam_api_key,
            model=config.sarvam_model,
            mode=config.sarvam_mode,
            language_code=config.sarvam_language_code,
        )
    except SarvamApiKeyMissingError as error:
        print(str(error), file=sys.stderr)
        return 2
    application = Application(config=config, adapter=adapter)
    application.start(start_capture=False)
    server = build_server(application=application, report_generator=_report_generator(config), port=args.port)
    print(f"[operator] browser API: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        application.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
