from __future__ import annotations

import json
import logging
import time

import pytest

from src.agent.feedback_agent import (
    FeedbackAgentError,
    FeedbackAgentWorker,
    build_classification_tool,
    classify_feedback,
    parse_classification_tool_call,
)


def test_agent_logs_lifecycle_without_feedback_or_secret(tmp_path, caplog):
    transcripts = tmp_path / "transcripts"
    classifications = tmp_path / "classifications"
    transcripts.mkdir()
    transcript_path = transcripts / "visitor_0001.json"
    feedback = "A private visitor transcript"
    secret = "test-api-secret"
    transcript_path.write_text(json.dumps({"text": feedback}), encoding="utf-8")

    def transport(**_kwargs):
        return {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "classify_feedback",
                        "arguments": json.dumps(
                            {
                                "feedback_text": feedback,
                                "projects_connections": [{"project_id": "ai_museum"}],
                            }
                        ),
                    },
                }
            ]
        }

    agent = FeedbackAgentWorker(
        transcripts_dir=transcripts,
        classifications_dir=classifications,
        catalog=[{"project_id": "ai_museum"}],
        api_key=secret,
        transport=transport,
    )
    with caplog.at_level(logging.INFO, logger="src.agent.feedback_agent"):
        agent.enqueue(transcript_path)
        agent._process(transcript_path)  # noqa: SLF001

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert '"event": "agent_wake"' in messages
    assert '"event": "agent_model_request"' in messages
    assert '"event": "agent_model_response"' in messages
    assert '"event": "agent_tool_call"' in messages
    assert '"event": "agent_classification_completed"' in messages
    assert feedback not in messages
    assert secret not in messages


def test_classify_feedback_keeps_multiple_unique_project_ids():
    result = classify_feedback(
        "The visitor discussed both exhibits.",
        [
            {"project_id": "ai_museum"},
            {"project_id": "vision_assist"},
            {"project_id": "ai_museum"},
        ],
    )
    assert result == {"project_ids": ["ai_museum", "vision_assist"]}


def test_classify_feedback_allows_no_project_match():
    assert classify_feedback("Nothing was specific.", []) == {"project_ids": []}


def test_classify_feedback_rejects_empty_feedback():
    with pytest.raises(FeedbackAgentError, match="feedback_text"):
        classify_feedback("  ", [])


def test_parse_tool_call_returns_arguments_for_one_expected_call():
    payload = {
        "content": "I found a relevant project.",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "classify_feedback",
                    "arguments": '{"feedback_text":"Great","projects_connections":[]}',
                },
            }
        ]
    }
    assert parse_classification_tool_call(payload) == {
        "feedback_text": "Great",
        "projects_connections": [],
    }


def test_parse_tool_call_rejects_multiple_calls():
    with pytest.raises(FeedbackAgentError, match="exactly one"):
        parse_classification_tool_call({"tool_calls": [{}, {}]})


def test_agent_retries_when_first_model_response_has_no_tool_call(tmp_path):
    transcripts = tmp_path / "transcripts"
    classifications = tmp_path / "classifications"
    transcripts.mkdir()
    transcript_path = transcripts / "visitor_0001.json"
    transcript_path.write_text(json.dumps({"text": "Great robot"}), encoding="utf-8")
    responses = iter(
        [
            {"tool_calls": []},
            {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "classify_feedback",
                            "arguments": '{"feedback_text":"Great robot","projects_connections":[]}',
                        },
                    }
                ]
            },
        ]
    )

    agent = FeedbackAgentWorker(
        transcripts_dir=transcripts,
        classifications_dir=classifications,
        catalog=[],
        api_key="test-key",
        transport=lambda **_kwargs: next(responses),
    )
    agent._process(transcript_path)  # noqa: SLF001

    artifact = json.loads((classifications / transcript_path.name).read_text(encoding="utf-8"))
    assert artifact["status"] == "completed"
    assert artifact["project_ids"] == []


def test_agent_requeues_failed_artifacts_but_skips_completed_artifacts(tmp_path):
    transcripts = tmp_path / "transcripts"
    classifications = tmp_path / "classifications"
    transcripts.mkdir()
    classifications.mkdir()
    for visitor_id in ("visitor_0001", "visitor_0002"):
        (transcripts / f"{visitor_id}.json").write_text(
            json.dumps({"text": visitor_id}), encoding="utf-8"
        )
    (classifications / "visitor_0001.json").write_text(
        json.dumps({"status": "failed", "error": "no tool call"}), encoding="utf-8"
    )
    (classifications / "visitor_0002.json").write_text(
        json.dumps({"status": "completed", "project_ids": []}), encoding="utf-8"
    )
    calls = []

    def transport(**kwargs):
        calls.append(kwargs["feedback_text"])
        return {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "classify_feedback",
                        "arguments": json.dumps(
                            {
                                "feedback_text": "visitor_0001",
                                "projects_connections": [],
                            }
                        ),
                    },
                }
            ]
        }

    agent = FeedbackAgentWorker(
        transcripts_dir=transcripts,
        classifications_dir=classifications,
        catalog=[],
        api_key="test-key",
        transport=transport,
    )
    agent.start()
    try:
        for _ in range(40):
            if json.loads((classifications / "visitor_0001.json").read_text(encoding="utf-8"))["status"] == "completed":
                break
            time.sleep(0.01)
    finally:
        agent.stop()

    assert calls == ["visitor_0001"]


def test_parse_tool_call_rejects_unknown_function():
    with pytest.raises(FeedbackAgentError, match="classify_feedback"):
        parse_classification_tool_call(
            {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "other_tool",
                            "arguments": "{}",
                        }
                    }
                ]
            }
        )


def test_parse_tool_call_rejects_extra_arguments():
    with pytest.raises(FeedbackAgentError, match="arguments"):
        parse_classification_tool_call(
            {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "classify_feedback",
                            "arguments": '{"feedback_text":"Great","projects_connections":[],"extra":true}',
                        },
                    }
                ]
            }
        )


def test_tool_definition_exposes_only_classification_function():
    definition = build_classification_tool()
    assert definition["type"] == "function"
    assert definition["function"]["name"] == "classify_feedback"
