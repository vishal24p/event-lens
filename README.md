# Event Lens

Event Lens is a local operator console for recording museum-visitor feedback, transcribing accepted recordings with Sarvam AI, and producing an evidence-based event report.

It runs as two local processes: a Python service controls microphone capture and processing, and a Next.js interface gives the operator a browser-based control panel. The local API listens only on `127.0.0.1`.

## Quick start

### 1. Install and configure

Use Python 3.10 or later, [uv](https://docs.astral.sh/uv/), and Node.js with npm.

```powershell
uv sync --extra dev
Copy-Item .env.example .env
Set-Content .env 'SARVAM_API_KEY=replace-with-your-key'
Set-Location ui
npm ci
Set-Location ..
```

`SARVAM_API_KEY` is required even for the configuration check because the application constructs the transcription adapter before it evaluates `--check-only`.

### 2. Start the local services

In one terminal, start the microphone and reporting API:

```powershell
uv run python -m src.operator_server
```

In another terminal, start the operator interface:

```powershell
Set-Location ui
npm run dev
```

Open the local URL printed by Next.js, normally `http://localhost:3000`.

### 3. Capture feedback and create a report

Select **Start recording**, then use **Save & next** for usable feedback, **Retry** to discard the current partial recording, or **Stop capture** when the session is over. Once all accepted recordings have finished transcribing, select **Report**.

The browser interface shows the recording state, elapsed time, microphone level, and when a report can be generated.

## Documentation

- [Operate Event Lens](docs/operations.md) for capture, reporting, and troubleshooting.
- [Reference](docs/reference.md) for commands, configuration, local API, and generated data.
- [Architecture](docs/architecture.md) for the processing lifecycle and design trade-offs.

## Verification

```powershell
uv run pytest
uv run event-lens --check-only
Set-Location ui
npm run build
```

The configuration check requires a valid `SARVAM_API_KEY`. The test suite uses a fake transcription adapter and does not call Sarvam.
