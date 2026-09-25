from __future__ import annotations

import pytest

from src.agent.feedback_agent import (
    FeedbackAgentError,
    build_classification_tool,
    classify_feedback,
    parse_classification_tool_call,
)


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
        "tool_calls": [
            {
                "id": "call_1",
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


def test_parse_tool_call_rejects_unknown_function():
    with pytest.raises(FeedbackAgentError, match="classify_feedback"):
        parse_classification_tool_call(
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "other_tool",
                            "arguments": "{}",
                        }
                    }
                ]
            }
        )


def test_tool_definition_exposes_only_classification_function():
    definition = build_classification_tool()
    assert definition["type"] == "function"
    assert definition["function"]["name"] == "classify_feedback"
