# Feedback-LLM — Phase 1

Operator-controlled audio feedback capture with Sarvam AI speech-to-text.
Single visitor at a time. Manual accept / discard / stop.

## Phase 1 scope

- One microphone, one visitor at a time.
- Operator keys: `ENTER` accept, `ESC` discard current, `Q` stop capture.
- Sequential processing queue. One transcription request at a time.
- Sarvam STT model: `saaras:v3` by default.
- No diarization, no streaming, no SQLite.

## 1. Install

```bash
uv sync
```

## Operator UI

The operator console is a separate browser-first Next.js app in `ui/`, built with HeroUI primitives and a 21st.dev-style copy-in composition while the backend remains Python-owned:

```bash
cd ui
npm install
npm run dev
```

Open `http://localhost:3000`. The current screen uses mock state for the three capture actions; backend API wiring comes next.

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

## 4. Run capture

```bash
uv run feedback-llm
```

Console:

```text
=== FEEDBACK CAPTURE SYSTEM ===
Data: data/

RECORDING: Visitor 0001
...

ENTER  Accept current visitor
ESC    Discard and retry current visitor
Q      Stop capture safely
```

## Output layout

```text
data/
  audio/        visitor_0001.wav, visitor_0002.wav, ...        (immutable)
  normalized/   visitor_0001.wav, visitor_0002.wav, ...
  quality/      visitor_0001.json, visitor_0002.json, ...
  transcripts/  visitor_0001.json, visitor_0002.json, ...
  queue.json    durable pending/transcribing/completed status
  reports/
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
uv run python -m src.reporting.cli report --data-root data
```

Each report uses only transcripts that have not appeared in an earlier report. `SARVAM_API_KEY` is required;
`SARVAM_LLM_MODEL` defaults to `sarvam-105b`.

## Report output layout

```text
data/
  transcripts/                         # Phase 1 output
  reports/
    manifest.json                      # transcript IDs already reported
    museum_event_report_*.json         # structured historical reports
    museum_event_report_*.md           # historical Markdown reports
    museum_event_report.md             # latest operator-readable report
```
