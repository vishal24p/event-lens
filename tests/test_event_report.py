from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.reporting.event_report import EventReportError, generate_event_report
from src.reporting.sarvam_client import SarvamResponse


CATALOG = {
    "projects": [
        {
            "project_id": "vision_assist",
            "short_name": "AI Blind Navigation System",
            "zone": {"number": "4"},
        }
    ]
}


def test_phase_two_report_uses_transcripts_and_writes_private_markdown(tmp_path: Path):
    transcript = "The blind navigation demonstration needs clearer spoken instructions."
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "visitor_0001.json").write_text(
        json.dumps({"visitor_id": "visitor_0001", "text": transcript}), encoding="utf-8"
    )
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        narrative = {
            "event_overview": "The session shows a clear usability improvement opportunity.",
            "findings": [{
                "project_id": "vision_assist",
                "outcome": "needs_attention",
                "finding": "Make the navigation guidance easier to follow during the demonstration.",
                "supporting_visitor_ids": ["visitor_0001"],
            }],
            "report_limitations": "This finding reflects only the feedback collected in this session.",
        }
        return SarvamResponse(body=narrative, content=json.dumps(narrative), actual_model="mock-model", raw_text="{}")

    outcome = generate_event_report(
        data_root=tmp_path,
        catalog=CATALOG,
        system_prompt="PROMPT",
        response_schema={"type": "object"},
        api_key="test-key",
        model="sarvam-105b",
        transport=fake_chat,
    )

    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    markdown = outcome.markdown_path.read_text(encoding="utf-8")
    assert seen["user_payload"]["transcripts"][0]["text"] == transcript
    assert seen["user_payload"]["project_catalog"] == CATALOG
    assert report["processing"] == {"requested_model": "sarvam-105b", "actual_model": "mock-model"}
    assert transcript not in markdown
    assert "visitor_0001" not in markdown
    assert markdown.startswith("# Event Feedback Report")

    with pytest.raises(EventReportError, match="no unreported"):
        generate_event_report(
            data_root=tmp_path,
            catalog=CATALOG,
            system_prompt="PROMPT",
            response_schema={"type": "object"},
            api_key="test-key",
            model="sarvam-105b",
            transport=fake_chat,
        )


def test_report_ignores_empty_transcript_files(tmp_path: Path):
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "visitor_0001.json").write_text(
        json.dumps({"visitor_id": "visitor_0001", "text": "Useful feedback."}), encoding="utf-8"
    )
    (transcripts / "visitor_0002.json").write_text(
        json.dumps({"visitor_id": "visitor_0002", "text": ""}), encoding="utf-8"
    )
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        body = {
            "event_overview": "Useful feedback was received.",
            "findings": [{
                "project_id": "vision_assist", "outcome": "working_well",
                "finding": "Visitors found the demonstration useful.",
                "supporting_visitor_ids": ["visitor_0001"],
            }],
            "report_limitations": "One empty transcription was ignored.",
        }
        return SarvamResponse(body=body, content=json.dumps(body), actual_model="mock-model", raw_text="{}")

    generate_event_report(
        data_root=tmp_path, catalog=CATALOG, system_prompt="PROMPT", response_schema={},
        api_key="test-key", model="sarvam-105b", transport=fake_chat,
    )

    assert seen["user_payload"]["transcripts"] == [{"visitor_id": "visitor_0001", "text": "Useful feedback."}]
