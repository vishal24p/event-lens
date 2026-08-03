"""Local browser-control API for the feedback capture application."""
from __future__ import annotations

import argparse
import json
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


def build_server(*, application: Application, report_generator: ReportGenerator, port: int = 8765) -> ThreadingHTTPServer:
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
