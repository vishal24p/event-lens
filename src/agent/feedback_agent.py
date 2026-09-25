"""Single-tool contract for transcript project classification."""
from __future__ import annotations

import json
import os
import queue
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TOOL_NAME = "classify_feedback"


class FeedbackAgentError(RuntimeError):
    """Raised when the agent returns an unsafe or invalid tool call."""


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


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
    if not isinstance(call, dict) or call.get("type") != "function":
        raise FeedbackAgentError("tool call must be a function")
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
    if set(parsed) != {"feedback_text", "projects_connections"}:
        raise FeedbackAgentError("tool call arguments have unexpected fields")
    if not isinstance(parsed["feedback_text"], str) or not isinstance(parsed["projects_connections"], list):
        raise FeedbackAgentError("tool call arguments have invalid fields")
    return parsed


def _sarvam_tool_transport(
    *,
    api_key: str,
    model: str,
    feedback_text: str,
    projects_connections: list[dict[str, Any]],
) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://api.sarvam.ai/v1/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "temperature": 0.0,
                "max_tokens": 2048,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Read the feedback and project catalog. Then make exactly one "
                            "classify_feedback tool call. Pass only projects explicitly "
                            "mentioned or clearly described by the feedback."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "feedback_text": feedback_text,
                                "projects_catalog": projects_connections,
                            },
                                ensure_ascii=False,
                            ),
                    },
                ],
                "tools": [build_classification_tool()],
                "tool_choice": {"type": "function", "function": {"name": TOOL_NAME}},
                "parallel_tool_calls": False,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as error:
        raise FeedbackAgentError(f"Sarvam tool call failed: {error}") from error
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as error:
        raise FeedbackAgentError("Sarvam response has no assistant message") from error
    return {"tool_calls": message.get("tool_calls")}


class FeedbackAgentWorker:
    def __init__(
        self,
        *,
        transcripts_dir: Path,
        classifications_dir: Path,
        catalog: list[dict[str, Any]],
        api_key: str,
        model: str | None = None,
        transport: Any = None,
    ) -> None:
        self._transcripts_dir = transcripts_dir
        self._classifications_dir = classifications_dir
        self._catalog = catalog
        self._catalog_ids = {item.get("project_id") for item in catalog}
        self._api_key = api_key
        self._model = model or os.environ.get("SARVAM_LLM_MODEL", "sarvam-105b")
        self._transport = transport or _sarvam_tool_transport
        self._jobs: queue.Queue[Path | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="feedback-agent", daemon=True)
        self._thread.start()
        for transcript_path in sorted(self._transcripts_dir.glob("visitor_*.json")):
            if not (self._classifications_dir / transcript_path.name).exists():
                self.enqueue(transcript_path)

    def enqueue(self, transcript_path: Path) -> None:
        if transcript_path.is_file():
            self._jobs.put(transcript_path)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._jobs.put(None)
        self._thread.join(timeout=30.0)
        self._thread = None

    def _loop(self) -> None:
        while True:
            transcript_path = self._jobs.get()
            if transcript_path is None:
                return
            self._process(transcript_path)

    def _process(self, transcript_path: Path) -> None:
        visitor_id = transcript_path.stem
        artifact_path = self._classifications_dir / transcript_path.name
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            feedback_text = transcript.get("text")
            if not isinstance(feedback_text, str) or not feedback_text.strip():
                raise FeedbackAgentError("transcript has no feedback text")
            response = self._transport(
                api_key=self._api_key,
                model=self._model,
                feedback_text=feedback_text,
                projects_connections=self._catalog,
            )
            arguments = parse_classification_tool_call(response)
            if arguments.get("feedback_text") != feedback_text:
                raise FeedbackAgentError("tool feedback_text does not match transcript")
            connections = arguments.get("projects_connections")
            result = classify_feedback(feedback_text, connections)
            unknown = [project_id for project_id in result["project_ids"] if project_id not in self._catalog_ids]
            if unknown:
                raise FeedbackAgentError(f"tool returned unknown projects: {unknown}")
            _write_json_atomic(
                artifact_path,
                {"visitor_id": visitor_id, "status": "completed", **result, "error": None},
            )
        except Exception as error:
            _write_json_atomic(
                artifact_path,
                {"visitor_id": visitor_id, "status": "failed", "project_ids": [], "error": str(error)},
            )
