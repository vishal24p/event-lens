# Spec: Live Feedback Project Classifier

## Objective

Add a separate agent-side feedback classifier for the operator console.
When a completed transcript JSON is written, a background agent worker wakes,
loads that transcript and the project catalog, lets the model understand the
state, and exposes exactly one custom tool:

```python
classify_feedback(
    feedback_text: str,
    projects_connections: list[ProjectConnection],
) -> list[str]
```

The model calls the tool after understanding the transcript. The tool returns
structured project IDs, never generated prose. Results are persisted separately
from the existing event report flow. A new feedback page shows every completed
transcript in a stack; selecting a transcript reveals its text and the linked
projects, including any number of projects.

The user/transcript is the primary entity. Projects are linked context.

## Tech Stack

- Python 3.10+, existing `threading`, `queue`, `json`, and `pathlib` modules.
- Sarvam Chat Completions V1 with `sarvam-105b`, using native function tools.
- The existing report client remains JSON-response-only; the agent gets a
  separate tool-call client so the flows do not collapse together.
- Existing Next.js 16 / React 19 / Tailwind UI.
- Existing pytest suite; no new dependency unless explicitly approved.

## Runtime Contract

1. `ProcessingWorker` writes `data/transcripts/visitor_NNNN.json`.
2. The transcript-save event enqueues that path for the new agent worker.
3. The agent worker reads the transcript JSON and current project catalog.
4. The model receives state and may call only `classify_feedback`.
5. The agent accepts the response only when it contains exactly one tool call
   with the expected function name; Sarvam's `parallel_tool_calls` flag is not
   treated as a guarantee for `sarvam-105b`.
6. The tool validates project inputs and returns zero or more valid project IDs.
7. The agent writes a separate classification artifact keyed by `visitor_id`.
8. Agent failure does not mark the transcript failed and does not block capture.
9. The feedback read endpoint returns all completed transcripts and any
   classification state in one response.

The existing report generator, report manifest, report endpoint, and report
validation remain unchanged.

## Data Contracts

### Tool input

`feedback_text` is the transcript text. `projects_connections` is a list,
possibly empty, of catalog-derived project objects containing at least
`project_id`, a display name, and aliases or other existing catalog connection
fields.

### Tool output

```json
{"project_ids": ["ai_museum", "vision_assist"]}
```

Returned IDs must exist in the supplied catalog, be unique, and preserve the
tool's order. Empty matches are valid.

### Classification artifact

```json
{
  "visitor_id": "visitor_0001",
  "status": "completed",
  "project_ids": ["ai_museum"],
  "error": null
}
```

Pending and failed classifications remain visible to the page without hiding
the transcript.

### Feedback endpoint

`GET /api/feedback` returns one payload containing all completed transcripts,
their segments, classification status, and linked project display data. The
browser makes one request for the page data and does not call the old report
endpoint.

### Agent logs

The worker emits JSON log events for `agent_wake`, `agent_model_request`,
`agent_model_response`, `agent_tool_call`, `agent_classification_completed`,
`agent_classification_failed`, `agent_worker_started`, and
`agent_worker_stopped`, plus `agent_tool_call_retry` when recovery is needed.
Events include visitor IDs, counts, model, and error types only; transcript
text, project catalog contents, and API credentials are never logged.

The classifier evaluates only the native `tool_calls` field. Assistant content
or reasoning may accompany a valid call and is ignored. The only accepted
result is exactly one `classify_feedback` call; text without a tool call and
multiple tool calls remain failures after one bounded recovery attempt. Failed
artifacts are retried when the worker starts again; completed artifacts are
skipped.

## Project Structure

```text
src/agent/                 New agent worker and single classification tool
src/pipeline/worker_v2.py  Emits transcript-ready event after atomic save
src/operator_server.py     Serves one feedback read endpoint
tests/                     Agent, projection, and endpoint coverage
ui/app/feedback/page.tsx   Transcript stack and detail view
ui/components/             Only if the existing UI patterns need a shared piece
docs/                      This spec and implementation plan
```

## Code Style

Prefer small typed data structures and explicit validation at boundaries:

```python
def classify_feedback(feedback_text: str, projects_connections: list[dict]) -> list[str]:
    if not feedback_text.strip():
        raise ValueError("feedback_text must not be empty")
    return _unique_known_project_ids(projects_connections)
```

Reuse existing catalog fields and HTTP response conventions. Keep the agent
worker asynchronous to capture, deterministic in file naming, and independent
from report-generation state.

## Testing Strategy

- Unit-test the single tool's validation: multiple matches, duplicate IDs,
  unknown IDs, and empty matches.
- Unit-test transcript-ready enqueueing and agent artifact persistence.
- Unit-test agent failure isolation: transcript remains completed and artifact
  records failure.
- Unit-test `/api/feedback` returns all transcripts and joins classifications by
  visitor ID, including one transcript linked to multiple projects.
- Run `pytest` for the Python suite.
- Run `npm run build` in `ui/` for the page/type check.
- Manually verify the feedback stack opens a transcript and reveals projects.

## Boundaries

- Always: keep transcript capture independent from agent failures; validate all
  project IDs against the catalog; use one browser data request; preserve
  accessibility for stack selection and expanded content.
- Ask first: new runtime dependencies, changes to the existing report contract,
  external services beyond the current Sarvam transport, or persistent schema
  migrations.
- Never: merge classifications into the event report manifest, overwrite the
  raw transcript, let the model invent project IDs, or expose arbitrary file
  paths through the browser endpoint.

## Success Criteria

- A completed transcript wakes the new agent worker without polling.
- `sarvam-105b` returns exactly one native `classify_feedback` tool call after
  receiving transcript state; text-only or extra-tool responses fail safely.
- One transcript can produce zero, one, or many valid project links.
- Classification artifacts are separate from reports and survive process restarts.
- The feedback page shows every completed transcript and expands linked projects.
- Existing capture, report, and test behavior remains green.

## Open Questions

None for the approved scope.
