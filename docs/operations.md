# Operator guide

Use this guide when running Event Lens during an event.

## Before the event

- Install Python 3.10+, `uv`, Node.js, and npm.
- Connect and test the microphone that will be used at the event.
- Add `SARVAM_API_KEY` to the repository's `.env` file. Keep this file private.
- Start the services and make one short test recording before visitors arrive.

Check the configuration without opening the microphone:

```powershell
uv run event-lens --check-only
```

## Start Event Lens

Start the Python service in one terminal:

```powershell
uv run python -m src.operator_server
```

Start the browser console in another terminal:

```powershell
Set-Location ui
npm run dev
```

Open the URL printed by Next.js. The console starts in the **Ready** state; it does not record until you select **Start recording**.

## Use an external microphone

Event Lens uses the computer's default microphone when no device is specified. To use an external microphone, first list the audio devices connected to the computer:

```powershell
uv run python -c "import sounddevice as sd; print(sd.query_devices())"
```

Choose the number at the start of the external microphone's row. It must have input channels; do not choose a row labelled **Output**. For example, if the external microphone is device `5`, start the Python service with:

```powershell
uv run python -m src.operator_server --input-device 5
```

To use the laptop microphone again, omit `--input-device`:

```powershell
uv run python -m src.operator_server
```

For a permanent workstation setup, set the chosen number in `config.toml`:

```toml
[storage]
input_device = 5
```

Run a short test recording after connecting or changing a microphone. Confirm that the input-level indicator moves before collecting real feedback.

## Record visitor feedback

Use the controls in the browser. Keyboard shortcuts are optional conveniences.

| Action | Browser shortcut | What happens |
| --- | --- | --- |
| Start recording | Enter | Starts recording the next visitor. |
| Save & next | Enter while recording | Saves the current WAV, queues it for processing, and immediately starts the next recording. |
| Save & pause | None | Saves the current WAV and returns to the ready state. |
| Retry | Escape | Discards the current partial recording and starts the same visitor ID again. |
| Stop capture | Q | Discards the active partial recording. Accepted recordings remain queued and continue processing. |
| Generate report | R | Creates a report when no recording or queue work remains. |
| Show help | ? | Opens the browser shortcut reference. |

Only saved recordings receive a permanent visitor ID. Retrying does not use up an ID.

## Generate the event report

1. Select **Stop capture** after the final visitor.
2. Wait for accepted recordings to finish transcribing.
3. Select **Report** when it becomes available.
4. Open the report from the browser, or use the Markdown file at `data/reports/event_feedback_report.md`.

The report includes only transcripts that have not already been reported. It describes supported findings rather than reproducing visitor quotes.

You can also generate the report from a terminal:

```powershell
uv run python -m src.reporting.cli report --data-root data
```

## Troubleshooting

### The browser cannot connect

Start `uv run python -m src.operator_server` and keep it running. The browser forwards `/api` requests to port 8765. If you start the server with another port, update the browser rewrite to match it.

### The microphone has no level

Confirm that the correct input device is selected in Windows. List devices with:

```powershell
uv run python -c "import sounddevice as sd; print(sd.query_devices())"
```

Then restart the service with the number of an **input** device. An output device cannot record feedback.

### A queue item failed

The queue shows failed items and their error messages. The original accepted WAV remains available in `data/audio` for diagnosis. Near-silent or invalid audio fails during normalisation; an empty transcription result also fails and is excluded from reports.

### The Report control is unavailable

Stop capture, then wait until all accepted recordings are finished. A report requires at least one completed, unreported transcript. The same transcript set is not reported twice because Event Lens records included visitor IDs in its manifest.

### Sarvam errors appear

Confirm `SARVAM_API_KEY` in `.env`, verify the network connection, then restart the Python service. Authentication, rate-limit, server, network, and invalid-response errors prevent the affected operation from completing.
