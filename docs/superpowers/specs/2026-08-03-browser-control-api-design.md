# Browser Control API Design

## Goal

Connect the operator website to the locally attached microphone and the existing Python capture pipeline so every visible value and action reflects persisted backend state.

## Constraints

- The Python process owns the microphone. The browser never requests or streams microphone audio.
- The UI and Python process run on the same laptop; the control server binds only to `127.0.0.1`.
- Preserve the operator controls: Save & next, Stop & retry, Stop session, and Start new session.
- Reports are manually generated from one or more operator-selected sessions.
- A report is an immutable snapshot. Generating again after a session receives more transcripts creates a new snapshot containing all completed transcripts selected at that later time.
- No simulated timer, waveform, visitors, queue state, history, or report values remain in the UI.

## Architecture

The existing `Application` remains the owner of `CaptureSession`, the processing queue, session storage, and transcription worker. A small Python HTTP server is started alongside it and provides local JSON endpoints. It uses the standard library, avoiding a second backend framework.

The Next.js UI calls the local API for commands and polls the status endpoint while it is open. The status response is the source of truth for the capture card. The browser renders an activity meter from backend peak samples; it never receives raw PCM or a WAV stream.

## Audio and Capture Flow

1. `POST /api/sessions` creates a session directory and starts the existing sounddevice input stream for `visitor_0001`.
2. The sounddevice callback copies each block to the existing writer queue and records its latest peak level under the capture lock.
3. `GET /api/status` returns the active visitor, elapsed duration, capture state, processing counts, and latest peak level.
4. `POST /api/capture/accept` finalizes the partial WAV, persists it as `visitor_NNNN.wav`, enqueues it, and begins the next visitor.
5. `POST /api/capture/discard` deletes the partial WAV and starts a fresh capture for the same visitor.
6. `POST /api/capture/stop` stops microphone capture, discards only the current partial WAV, and leaves accepted items to drain through transcription.

## API Contract

All responses use JSON. Mutating routes return the current status payload. Invalid transitions return HTTP 409 with `{ "error": "..." }`; malformed requests return HTTP 400.

- `GET /api/status`
  - Returns `capture_state` (`idle`, `recording`, `stopped`, `draining`), `session_id`, `started_at`, `current_visitor_id`, `elapsed_seconds`, `meter_peak`, `queue`, and `accepted_count`.
- `POST /api/sessions`
  - Starts a new session. Returns 409 while an existing session is recording or draining.
- `POST /api/capture/accept`
  - Saves the current take and starts the next visitor. Returns 409 unless recording.
- `POST /api/capture/discard`
  - Discards and restarts the current take. Returns 409 unless recording.
- `POST /api/capture/stop`
  - Stops capture safely. Repeated calls return the stopped/draining status without changing saved audio.
- `GET /api/sessions`
  - Lists real session directories with start time, capture state when current, accepted audio count, completed transcript count, and report snapshots.
- `POST /api/reports`
  - Accepts `{ "session_ids": ["session_..."] }`. Reads completed transcript files from every selected session and creates a new immutable report snapshot under `reports/report_<UTC timestamp>/`.
- `GET /api/reports/<report_id>`
  - Returns the structured saved report for display.

## Manual Report Snapshots

The existing single-session report generator remains available for its CLI. A new multi-session entry point collects completed transcript JSON files from the selected session roots, calls Sarvam once with the combined evidence, and writes:

```text
reports/
  report_YYYY-MM-DD_HH-MM-SS/
    report.json
    report.md
    source.json
```

`source.json` records the selected session IDs, transcript visitor IDs, and generation timestamp. An in-progress session contributes only completed transcripts. A later manual report for that same session reads all currently completed transcripts again, including those produced after the earlier snapshot.

## UI Behavior

- The capture page fetches initial status and polls it every 250 ms. There is no local elapsed-time interval or local visitor/session archive.
- Buttons and keyboard shortcuts call their matching API routes, then render the returned status. Disabled states come from `capture_state`.
- The waveform uses the returned peak samples. An idle or stopped backend produces an idle waveform.
- The report screen loads `/api/sessions`, lets the operator select real sessions, calls `/api/reports`, and displays the saved report returned by the API. Print/download use the returned saved report, not a browser-created summary.

## Error Handling

- Capture errors, worker failures, and report-generation failures are exposed as backend messages and shown in the UI without inventing a success state.
- A report cannot be generated for an empty selection or for selected sessions with no completed transcripts.
- The UI shows an unavailable-backend state when `GET /api/status` fails; capture actions remain disabled until the local Python process is reachable.

## Verification

- Python API tests cover lifecycle transitions, status serialization, report selection validation, report snapshot inputs, and invalid-action responses using fake capture/transcription dependencies.
- Existing report tests continue to cover the single-session CLI path.
- The Next.js production build verifies the UI compiles against the new API contract.
