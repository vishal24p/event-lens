# Feedback-LLM — Phase 1

Operator-controlled audio feedback capture with Sarvam AI speech-to-text.
Single visitor at a time. Manual accept / discard / stop.

## Phase 1 scope

- One microphone, one visitor at a time.
- Operator keys: `ENTER` accept, `ESC` discard current, `Q` stop capture.
- Sequential processing queue. One transcription request at a time.
- Sarvam STT model: `saaras:v3` by default.
- No diarization, no streaming, no frontend, no SQLite.

## 1. Install

```bash
uv sync
```

## 2. Configure Sarvam AI

Create a `.env` file from the example and enter your Sarvam API key:

```bash
cp .env.example .env
```

Set `SARVAM_API_KEY=...`. The default transcription model is `saaras:v3`.
Set `SARVAM_STT_MODEL` only if you need to change it.

## 3. Validate configuration

```bash
uv run feedback-llm --check-only
```

Prints the effective Sarvam transcription model and mode.

## 4. Run a session

```bash
uv run feedback-llm
```

Console:

```text
=== FEEDBACK CAPTURE SYSTEM ===
Session: session_2026-07-22_14-30-00

RECORDING: Visitor 0001
...

ENTER  Accept current visitor
ESC    Discard and retry current visitor
Q      Stop capture safely
```

## Output layout

```text
sessions/
  session_YYYY-MM-DD_HH-MM-SS/
    audio/        visitor_0001.wav, visitor_0002.wav, ...        (immutable)
    normalized/   visitor_0001.wav, visitor_0002.wav, ...
    quality/      visitor_0001.json, visitor_0002.json, ...
    transcripts/  visitor_0001.json, visitor_0002.json, ...
    session.json
```

`Q` stops new capture, discards only the current partial, and lets the queue
drain before exiting.

## Tests

```bash
uv run pytest -q
```

Tests use a fake transcription adapter. They do not require a microphone,
GPU, or the real model.

# Phase 2 — AI Museum Report

Phase 2 reads all completed Phase 1 transcripts and the museum project catalog,
then makes one Sarvam `sarvam-105b` call to produce an evidence-based report of
what worked, what needs attention, and where feedback was mixed.

It writes both a structured JSON report and a human-readable Markdown report.
The final Markdown contains museum findings only—never visitor IDs, quotations,
or transcript text.

## Run Phase 2

```bash
uv run python -m src.reporting.cli report --session sessions/session_2026-07-22_14-30-00
```

Use `--force` to regenerate an existing report. `SARVAM_API_KEY` is required;
`SARVAM_LLM_MODEL` defaults to `sarvam-105b`.

## Output layout (per session)

```text
sessions/
  session_YYYY-MM-DD_HH-MM-SS/
    transcripts/                       # Phase 1 output
    reports/
      museum_event_report.json         # structured report
      museum_event_report.md           # operator-readable report
      museum_event_report.response.*   # private model response for audit
```
