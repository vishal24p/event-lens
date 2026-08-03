from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.reporting.event_report import EventReportExistsError, generate_event_report
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
            "museum_overview": "The session shows a clear usability improvement opportunity.",
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
        session_root=tmp_path,
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
    assert report["processing"]["phase"] == "phase_2_museum_report"
    assert transcript not in markdown
    assert "visitor_0001" not in markdown

    with pytest.raises(EventReportExistsError):
        generate_event_report(
            session_root=tmp_path,
            catalog=CATALOG,
            system_prompt="PROMPT",
            response_schema={"type": "object"},
            api_key="test-key",
            model="sarvam-105b",
            transport=fake_chat,
        )
