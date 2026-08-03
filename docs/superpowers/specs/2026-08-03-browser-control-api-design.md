# Browser Control API Design

## Goal

Connect the browser operator console to the Python capture pipeline so it shows real capture state, controls recording, and generates museum reports.

## Constraints

- The microphone is attached to the same laptop as the Python process.
- Python remains the only component that accesses the microphone and writes audio.
- The browser never captures, uploads, or receives raw audio.
- Keep the operator actions: Start recording, Save & next (Enter), Save & pause, Retry (Escape), and Stop capture (Q).
- All feedback uses one global durable queue; there is no session selection or per-session queue.
- No simulated timer, waveform, session history, or visitor count may remain in the UI.
- Reuse the existing capture, queue, storage, transcription, and reporting pipeline. Do not add a second processing path.

## Existing Architecture

`Application` opens the global `data/` directory and starts one `ProcessingWorker`. `CaptureSession` reads the attached microphone through `sounddevice`, writes blocks to a partial WAV, then either deletes it on retry or moves it to `data/audio/visitor_NNNN.wav` on save. `data/queue.json` stores queue state atomically. On restart, interrupted work becomes pending again, while completed transcript files are not sent to Sarvam again. The worker writes normalized WAV, quality JSON, and transcript JSON. `generate_event_report` uses transcripts not recorded in `data/reports/manifest.json` and writes a structured JSON and Markdown report.

## Architecture

The localhost-only Python HTTP API owns one long-lived `Application` instance. The API invokes public lifecycle methods and returns a thread-safe status snapshot. The Next.js browser app polls the status endpoint and sends action requests; it contains no microphone, transcript, queue, or report state beyond request loading and error display.

The backend publishes a small numeric input level calculated in the existing audio callback. The browser converts those real samples into the existing waveform presentation. No PCM or WAV data crosses the HTTP boundary.

## API

### Capture

- `GET /api/status` returns capture state, current visitor ID, elapsed seconds, real input level, and queue item snapshots.
- `POST /api/capture/start` begins recording the next visitor.
- `POST /api/capture/accept` finalizes the current take, persists the WAV, enqueues processing, and begins the next visitor.
- `POST /api/capture/accept-and-pause` finalizes and queues the current take, then returns capture to idle.
- `POST /api/capture/discard` deletes the current partial take and restarts the same visitor.
- `POST /api/capture/stop` stops capture, discards the current partial take, and leaves accepted queue items to drain.
- `POST /api/report` creates a report from completed transcripts not used by an earlier report; `GET /api/report/markdown` returns the latest Markdown report.

Every state-changing endpoint returns the current status. Invalid state transitions return a clear 409 response; unexpected capture or processing errors return a 500 response without fabricating a replacement state.

## Data flow

```text
Attached microphone
  -> CaptureSession callback
  -> partial WAV + current input-level snapshot
  -> save: immutable raw WAV
  -> durable data/queue.json
  -> normalized WAV + quality JSON + transcript JSON
  -> browser status view
```

## Browser changes

- Replace the local React timer, counters, visitor IDs, generated waveform, and report state with API responses.
- Keep keyboard shortcuts, but route them to the same API actions as the buttons.
- Disable buttons while an action request is in flight; show the backend's returned state or error.
- Remove UI controls and screens that are not part of the capture/report workflow.

## Testing

- Unit-test lifecycle methods, durable queue recovery, report-manifest filtering, and status snapshots using the existing fake transcription adapter; no microphone or Sarvam request is required.
- Test API action state transitions, including invalid transitions.
- Test input-level calculation from a supplied audio block.
- Build the Next.js app and verify it contains no `Source: simulated`, generated timer, generated queue/archive, report overlay, or synthetic waveform implementation.
