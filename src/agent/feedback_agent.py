"""Single-tool contract for transcript project classification."""
from __future__ import annotations

import json
from typing import Any


TOOL_NAME = "classify_feedback"


class FeedbackAgentError(RuntimeError):
    """Raised when the agent returns an unsafe or invalid tool call."""


def build_classification_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Connect feedback to the projects explicitly mentioned in it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feedback_text": {"type": "string"},
                    "projects_connections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "project_id": {"type": "string"},
                                "name": {"type": "string"},
                            },
                            "required": ["project_id"],
                            "additionalProperties": True,
                        },
                    },
                },
                "required": ["feedback_text", "projects_connections"],
                "additionalProperties": False,
            },
        },
    }


def classify_feedback(
    feedback_text: str,
    projects_connections: list[dict[str, Any]],
) -> dict[str, list[str]]:
    if not isinstance(feedback_text, str) or not feedback_text.strip():
        raise FeedbackAgentError("feedback_text must not be empty")
    if not isinstance(projects_connections, list):
        raise FeedbackAgentError("projects_connections must be a list")

    project_ids: list[str] = []
    for connection in projects_connections:
        if not isinstance(connection, dict):
            raise FeedbackAgentError("each project connection must be an object")
        project_id = connection.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise FeedbackAgentError("each project connection needs a project_id")
        if project_id not in project_ids:
            project_ids.append(project_id)
    return {"project_ids": project_ids}


def parse_classification_tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    calls = payload.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1:
        raise FeedbackAgentError("agent must return exactly one tool call")
    call = calls[0]
    function = call.get("function") if isinstance(call, dict) else None
    if not isinstance(function, dict) or function.get("name") != TOOL_NAME:
        raise FeedbackAgentError(f"agent must call {TOOL_NAME}")
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        raise FeedbackAgentError("tool call arguments must be JSON text")
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise FeedbackAgentError("tool call arguments are invalid JSON") from error
    if not isinstance(parsed, dict):
        raise FeedbackAgentError("tool call arguments must be an object")
    return parsed
