# How to operate Event Lens

This guide takes an operator from a ready workstation to a generated feedback report.

## Prerequisites

- Python 3.10 or later and `uv`.
- Node.js and npm for the browser console.
- A microphone available to the local machine.
- A Sarvam API key in the repository's `.env` file:

  ```dotenv
  SARVAM_API_KEY=your-key
  ```

The key is used for both transcription and report generation. Keep `.env` private.

## Start an operator session

1. Start the local Python service.

   ```powershell
   uv run python -m src.operator_server
   ```

   It starts the capture pipeline without opening a recording and listens at `http://127.0.0.1:8765`.

2. Start the browser console in another terminal.

   ```powershell
   Set-Location ui
   npm run dev
   ```

   Next.js forwards browser requests under `/api` to the local Python service.

3. Open the URL printed by Next.js and select **Start recording**. The status should change to **Recording** and show a visitor ID such as `visitor_0001`.

## Capture visitor feedback

While a recording is active, use either the screen controls or the keyboard:

| Action | Browser key | Terminal key | Result |
| --- | --- | --- | --- |
| Save & next | Enter | Enter | Saves the WAV, queues it for processing, advances the visitor ID, and immediately begins the next recording. |
| Save & pause | None | None | Saves the WAV and returns the console to the ready state. |
| Retry | Escape | Escape | Deletes the current partial recording and starts the same visitor ID again. |
| Stop capture | Q | Q | Deletes the active partial recording and lets already accepted recordings finish processing. |
| Generate report | R | None | Creates a report when capture is stopped and all queued recordings have completed. |
| Show keyboard help | ? | None | Opens the shortcut reference in the browser. |

Only a saved recording gets a permanent visitor number. Retrying does not consume an ID. If a microphone callback queue fills, the capture process preserves the newest audio blocks rather than blocking the real-time callback.

## Generate a report

Stop capture and wait for the queue to drain. The **Report** control becomes available only when no recording is active, no item is pending or processing, and at least one completed transcript has not already been reported.

Select **Report**, then use **Open report** in the browser. The report deliberately contains findings rather than raw visitor quotations or visitor identifiers.

You can also generate a report from the command line:

```powershell
uv run python -m src.reporting.cli report --data-root data
```

The report command accepts only `sarvam-105b`; it exits without sending traffic when `SARVAM_API_KEY` is missing.

## Check configuration before an event

```powershell
uv run event-lens --check-only
```

This confirms the resolved Sarvam transcription model and mode. It does not open the microphone or start capture.

## Troubleshooting

### The browser says the backend is unavailable

Start `uv run python -m src.operator_server` and leave it running. The browser is configured to forward `/api` calls to port 8765; a different `--port` value requires matching the frontend rewrite.

### A recording cannot be saved

An accepted recording must contain written audio. Empty or invalid partial WAV files are removed and the current visitor ID is retained. Check that the correct input device is selected and that its level changes in the browser.

### A queue item failed

The operator status shows the last three failures. The original accepted WAV remains available for diagnosis. Near-silent or invalid audio fails during normalization; empty transcription results also fail and do not create transcript files.

### Report generation is unavailable

Stop capture, wait until pending and in-flight work complete, and confirm a completed transcript has not already been included in a prior report. A report cannot be regenerated from exactly the same transcript set because Event Lens records reported visitor IDs in its manifest.

### Sarvam authentication or network errors occur

Verify `SARVAM_API_KEY` in `.env`, then restart the Python service. Authentication failures are reported for HTTP 401/403; rate limits, server errors, invalid provider responses, and network failures also prevent report creation.
