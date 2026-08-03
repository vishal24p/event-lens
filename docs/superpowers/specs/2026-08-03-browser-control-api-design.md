# Browser Control API Design

## Goal

Connect the browser operator console to the existing Python capture pipeline so it shows and controls only real microphone, session, processing, transcript, and report data.

## Constraints

- The microphone is attached to the same laptop as the Python process.
- Python remains the only component that accesses the microphone and writes audio.
- The browser never captures, uploads, or receives raw audio.
- Keep the existing operator actions: Save & next, Stop & retry, Stop session, and Start new session.
- Report generation is manual. An operator selects one or more real sessions and explicitly generates a saved report snapshot.
- No simulated timer, waveform, session history, visitor count, or report data may remain in the UI.
- Reuse the existing capture, queue, storage, transcription, and reporting pipeline. Do not add a second processing path.

## Existing Architecture

`Application` creates a session directory, starts `CaptureSession` for the current visitor, and starts one `ProcessingWorker`. `CaptureSession` reads the attached microphone through `sounddevice`, writes blocks to a partial WAV, then either deletes it on retry or moves it to `audio/visitor_NNNN.wav` on save. The queue and worker produce normalized WAV, quality JSON, and transcript JSON. `generate_event_report` reads completed transcript JSON files and writes a structured JSON and Markdown report.

## Architecture

Add a localhost-only Python HTTP API that owns one long-lived `Application` instance. The API invokes public lifecycle methods on that instance and returns a thread-safe status snapshot. The Next.js browser app polls the status endpoint and sends action requests; it contains no capture/session/report state beyond request loading and error display.

The backend publishes a small numeric input level calculated in the existing audio callback. The browser converts those real samples into the existing waveform presentation. No PCM or WAV data crosses the HTTP boundary.

## API

### Capture

- `GET /api/status` returns the active session ID, capture state, current visitor ID, elapsed seconds, real input level, and queue item snapshots.
- `POST /api/capture/start` creates a new session and starts microphone capture only when no capture session is active.
- `POST /api/capture/accept` finalizes the current take, persists the WAV, enqueues processing, and begins the next visitor.
- `POST /api/capture/discard` deletes the current partial take and restarts the same visitor.
- `POST /api/capture/stop` stops capture, discards the current partial take, and leaves accepted queue items to drain.

Every state-changing endpoint returns the current status. Invalid state transitions return a clear 409 response; unexpected capture or processing errors return a 500 response without fabricating a replacement state.

### Sessions and reports

- `GET /api/sessions` reads real session directories and returns session metadata, accepted audio count, completed transcript count, and active/finished state.
- `POST /api/reports` accepts selected session IDs and manually generates a report snapshot from completed transcripts in all selected sessions.
- `GET /api/reports/{report_id}` returns a saved report snapshot.

Multi-session report generation uses the current completed transcript set from every selected session. A report generated mid-session is immutable: it contains only transcripts complete at generation time. When the operator generates another report after further capture, the backend reads the same selected sessions again and includes the new transcripts as well. Reports are timestamped snapshots; generating a later report never rewrites an earlier one.

## Data flow

```text
Attached microphone
  -> CaptureSession callback
  -> partial WAV + current input-level snapshot
  -> save: immutable raw WAV
  -> ProcessingQueue
  -> normalized WAV + quality JSON + transcript JSON
  -> manual selected-session report snapshot
  -> browser status/session/report views
```

## Browser changes

- Replace the local React timer, counters, visitor IDs, session archive, and generated waveform with API responses.
- Keep keyboard shortcuts, but route them to the same API actions as the buttons.
- Disable buttons while an action request is in flight; show the backend's returned state or error.
- Populate the session/report UI only from `/api/sessions` and report endpoints.

## Testing

- Unit-test the new lifecycle methods and status snapshots using the existing fake transcription adapter; no microphone or Sarvam request is required.
- Test API action state transitions, including an invalid transition.
- Test input-level calculation from a supplied audio block.
- Test multi-session transcript collection and report snapshot paths, including a second report generated after additional transcripts appear.
- Build the Next.js app and verify it contains no `Source: simulated`, generated timer, generated session archive, or synthetic waveform implementation.
