"""Phase 2 CLI: create the final AI Museum report from Phase 1 transcripts."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .event_report import EventReportError, generate_event_report
from .sarvam_client import SarvamError, get_api_key


DEFAULT_MODEL = "sarvam-105b"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(root: Path, relative_path: str) -> dict:
    return json.loads((root / relative_path).read_text(encoding="utf-8"))


def _load_catalog(root: Path) -> dict:
    path = "context/project_catalog_pending_zones.json"
    if not (root / path).is_file():
        path = "context/museum_catalog.json"
    return _load_json(root, path)


def main(argv: Optional[list[str]] = None) -> int:
    root = _project_root()
    load_dotenv(root / ".env")
    parser = argparse.ArgumentParser(prog="python -m src.reporting.cli", description="Phase 2 AI Museum report CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    report = subparsers.add_parser("report", help="Generate the final museum report from Phase 1 transcripts")
    report.add_argument("--session", type=Path, required=True)
    report.add_argument("--model", default=os.environ.get("SARVAM_LLM_MODEL", DEFAULT_MODEL))
    report.add_argument("--force", action="store_true", help="Regenerate an existing report")
    args = parser.parse_args(argv)
    session_root = args.session.resolve()
    if not session_root.is_dir():
        print(f"error: session path not found: {session_root}", file=sys.stderr)
        return 2
    if args.model != DEFAULT_MODEL:
        print("error: --model must be sarvam-105b", file=sys.stderr)
        return 2
    api_key = get_api_key()
    if not api_key:
        print("error: SARVAM_API_KEY is not set. Refusing to send real traffic.", file=sys.stderr)
        return 3
    try:
        print(f"[phase 2 report] provider: Sarvam AI; model: {args.model}")
        outcome = generate_event_report(
            session_root=session_root,
            catalog=_load_catalog(root),
            system_prompt=(root / "prompts" / "museum_event_report_v1.txt").read_text(encoding="utf-8"),
            response_schema=_load_json(root, "schemas/museum_event_report_v1.json"),
            api_key=api_key,
            model=args.model,
            force=args.force,
        )
    except (EventReportError, SarvamError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"[phase 2 report] completed: {outcome.report_path}, {outcome.markdown_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
