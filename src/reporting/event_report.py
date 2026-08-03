"""Generate the Phase 2 AI Museum findings report from Phase 1 transcripts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import sarvam_client
from .sarvam_client import SarvamResponse


REPORT_VERSION = "2.0"
MANIFEST_VERSION = "1.0"
OUTCOMES = ("working_well", "needs_attention", "mixed_feedback")


class EventReportError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventReportOutcome:
    report_path: Path
    markdown_path: Path
    actual_model: str


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _project_index(catalog: dict) -> dict[str, dict]:
    projects = catalog.get("projects", [])
    if not isinstance(projects, list):
        raise EventReportError("catalog projects must be a list")
    index = {}
    for project in projects:
        project_id = project.get("project_id") if isinstance(project, dict) else None
        if not isinstance(project_id, str) or not project_id or project_id in index:
            raise EventReportError("catalog must contain unique project_id values")
        index[project_id] = project
    if not index:
        raise EventReportError("catalog must contain at least one project")
    return index


def _read_transcripts(transcripts_dir: Path, *, excluded_visitor_ids: set[str] | None = None) -> list[dict]:
    if not transcripts_dir.is_dir():
        raise EventReportError(f"transcripts directory not found: {transcripts_dir}")
    transcripts = []
    for path in sorted(transcripts_dir.glob("visitor_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EventReportError(f"invalid transcript file {path.name}: {error}") from error
        visitor_id, text = payload.get("visitor_id"), payload.get("text")
        if not isinstance(visitor_id, str) or not isinstance(text, str) or not text.strip():
            raise EventReportError(f"transcript file {path.name} has no visitor_id or text")
        if visitor_id not in (excluded_visitor_ids or set()):
            transcripts.append({"visitor_id": visitor_id, "text": text})
    return transcripts


def _manifest(reports_dir: Path) -> dict:
    path = reports_dir / "manifest.json"
    if not path.is_file():
        return {"manifest_version": MANIFEST_VERSION, "reports": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EventReportError(f"invalid report manifest: {error}") from error
    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise EventReportError("invalid report manifest reports")
    return payload


def _reported_visitor_ids(manifest: dict) -> set[str]:
    visitor_ids = set()
    for report in manifest.get("reports", []):
        if isinstance(report, dict):
            ids = report.get("visitor_ids", [])
            if isinstance(ids, list):
                visitor_ids.update(visitor_id for visitor_id in ids if isinstance(visitor_id, str))
    return visitor_ids


def has_unreported_transcripts(data_root: Path) -> bool:
    try:
        reports_dir = data_root / "reports"
        return bool(_read_transcripts(data_root / "transcripts", excluded_visitor_ids=_reported_visitor_ids(_manifest(reports_dir))))
    except EventReportError:
        return False


def _validate_narrative(*, narrative: dict, project_ids: set[str], visitor_ids: set[str]) -> None:
    if not isinstance(narrative, dict):
        raise EventReportError("report response is not a JSON object")
    for field in ("museum_overview", "report_limitations"):
        if not isinstance(narrative.get(field), str) or not narrative[field].strip():
            raise EventReportError(f"report response has no {field}")
    findings = narrative.get("findings")
    if not isinstance(findings, list):
        raise EventReportError("report response has invalid findings")
    seen = set()
    for item in findings:
        if not isinstance(item, dict):
            raise EventReportError("report response has invalid finding")
        project_id, outcome = item.get("project_id"), item.get("outcome")
        supporting_ids = item.get("supporting_visitor_ids")
        if not isinstance(project_id, str) or project_id not in project_ids or project_id in seen:
            raise EventReportError("report response has an invalid project finding")
        if outcome not in OUTCOMES or not isinstance(item.get("finding"), str) or not item["finding"].strip():
            raise EventReportError("report response has an invalid finding")
        if not isinstance(supporting_ids, list) or not supporting_ids or not all(
            isinstance(visitor_id, str) and visitor_id in visitor_ids for visitor_id in supporting_ids
        ):
            raise EventReportError("report response finding has unknown supporting visitor")
        seen.add(project_id)


def _markdown(report: dict, catalog: dict) -> str:
    projects = _project_index(catalog)
    labels = {"working_well": "Working well", "needs_attention": "Needs attention", "mixed_feedback": "Mixed feedback"}
    lines = ["# AI Museum Event Report", "", f"**Report:** {report['report_id']}", "", "## Museum overview", "", report["narrative"]["museum_overview"]]
    for outcome in OUTCOMES:
        matching = [item for item in report["narrative"]["findings"] if item["outcome"] == outcome]
        lines.extend(["", f"## {labels[outcome]}", ""])
        if not matching:
            lines.append("No direct finding was generated for this category.")
        for item in matching:
            project = projects[item["project_id"]]
            name = project.get("short_name") or project.get("official_name") or item["project_id"]
            lines.append(f"- **{name}** (Zone {project.get('zone', {}).get('number', '?')}): {item['finding']}")
    lines.extend(["", "## Report limitations", "", report["narrative"]["report_limitations"], ""])
    return "\n".join(lines)


def generate_event_report(
    *, data_root: Path, catalog: dict, system_prompt: str, response_schema: dict, api_key: str,
    model: str, transport: Optional[Callable[..., SarvamResponse]] = None,
) -> EventReportOutcome:
    reports_dir = data_root / "reports"
    manifest = _manifest(reports_dir)
    transcripts = _read_transcripts(
        data_root / "transcripts", excluded_visitor_ids=_reported_visitor_ids(manifest)
    )
    if not transcripts:
        raise EventReportError("no unreported completed transcripts found")
    report_id = f"museum_event_report_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S_%f')}"
    report_path = reports_dir / f"{report_id}.json"
    markdown_path = reports_dir / f"{report_id}.md"
    project_ids = set(_project_index(catalog))
    response = (transport or sarvam_client.chat)(
        api_key=api_key, model=model, system_prompt=system_prompt,
        user_payload={"report_id": report_id, "museum_catalog": catalog, "transcripts": transcripts},
        response_schema=response_schema,
    )
    _write_text(reports_dir / f"{report_id}.response.txt", response.content)
    _write_json(reports_dir / f"{report_id}.response.json", response.body)
    _validate_narrative(narrative=response.body, project_ids=project_ids, visitor_ids={item["visitor_id"] for item in transcripts})
    report = {
        "report_version": REPORT_VERSION,
        "report_id": report_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "narrative": response.body,
        "processing": {"phase": "phase_2_museum_report", "requested_model": model, "actual_model": response.actual_model},
    }
    _write_json(report_path, report)
    markdown = _markdown(report, catalog)
    _write_text(markdown_path, markdown)
    _write_text(reports_dir / "museum_event_report.md", markdown)
    manifest["manifest_version"] = MANIFEST_VERSION
    manifest.setdefault("reports", []).append(
        {"report_id": report_id, "generated_at": report["generated_at"], "visitor_ids": [item["visitor_id"] for item in transcripts]}
    )
    _write_json(reports_dir / "manifest.json", manifest)
    return EventReportOutcome(report_path=report_path, markdown_path=markdown_path, actual_model=response.actual_model)
