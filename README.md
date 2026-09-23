# Event Lens

An AI pipeline that turns raw spoken visitor feedback into a structured, evidence-validated report per exhibit — automatically, with no human summarization step.

The system is the pipeline: audio capture engine → durable processing queue → speech-to-text → an LLM report-generation engine that is constrained and independently validated before its output is trusted. The operator console (terminal or browser) is a thin control surface for recording.

Deployed and run live as the feedback-collection station for the AI Museum event at Knowledge Institute of Technology. `data/queue.json` in this repo is the actual queue state from that run: 15 visitor recordings captured, 10 transcribed successfully, 5 auto-rejected for near-silence before ever reaching the speech-to-text API — a cost-avoidance decision made by the pipeline itself, not by an operator.

## The engine

This is the part that does the actual work. Everything else in the repo exists to feed it or expose it.

### 1. Capture & durability engine (`src/audio/`, `src/pipeline/`, `src/storage/`)

- The PortAudio callback and the disk-writing thread are strictly separated, so audio capture can never block on I/O — the callback only copies a buffer onto a bounded queue and returns.
- Every accepted recording enters a durable, JSON-persisted FIFO queue. Every status change is written atomically (temp file + `os.replace`), so the process can be killed at any point without corrupting queue state.
- On restart, the queue reconciles itself against what's actually on disk: a transcript file present forces `completed` regardless of last-known status; a missing raw WAV forces `failed`; anything mid-flight with its raw WAV intact resets to `pending` and re-runs. No manual recovery step, no re-transcribing completed work, no silently lost recordings.
- The worker is single-threaded and strictly sequential (FIFO), and normalization/quality-checking happens *before* any external API call — a recording that fails the near-silence check never reaches Sarvam. This is what produced the 5 zero-cost rejections in the real event run.
- The raw accepted WAV is never modified or deleted by any downstream step, success or failure.

### 2. Speech-to-text integration (`src/stt/`)

- Wraps Sarvam AI's `saaras:v3` behind a small `TranscriptionAdapter` protocol, so the rest of the system — and the entire test suite — never depends on the SDK directly.
- Routes automatically by clip duration: Sarvam's synchronous REST endpoint for clips ≤30s, the asynchronous batch job API (upload → start → poll → download) for anything longer.
- Reconstructs word-level segments from Sarvam's timestamp data when available, and degrades gracefully to a single whole-transcript segment when it isn't — callers never have to branch on which case they got.

### 3. Report generation engine (`src/reporting/`) — the core deliverable

A single LLM call is asked to read every visitor transcript plus a catalog of exhibit projects and produce a structured, per-exhibit evidence report. The engineering problem here isn't calling an LLM — it's making its output trustworthy enough to hand to event organisers as a record of what actually happened.

**The prompt (`prompts/event_feedback_report_v1.txt`) is a closed evidentiary contract, not a loose instruction:**
- Transcripts are the only allowed source of *experience* claims; the project catalog is only allowed to resolve *which* project a visitor meant.
- Explicit ban on outside knowledge, invented projects, invented visitors, invented causes, and treating "no feedback" as a negative signal.
- One finding per project maximum, three allowed outcomes (`working_well` / `needs_attention` / `mixed_feedback`), scoped strictly to this event — never a prediction about future performance.
- No verbatim quoting, no recommendations, no transcript-by-transcript summary.

**The code does not trust the model to have followed the prompt.** `_validate_narrative()` independently re-checks the parsed response against ground truth the model doesn't control: every `project_id` must exist in the real catalog passed in for *this* call, every `supporting_visitor_ids` entry must be a real visitor ID from the real transcript set for *this* run, every outcome must be one of the three allowed values, no project appears twice. Any violation raises an error and no report is written — a plausible-sounding but ungrounded model response is rejected exactly like a malformed one.

**Incremental, auditable, deterministic:**
- A `manifest.json` tracks which visitor IDs have already been reported. Each run only sends *unreported* transcripts — running the report command again after more visitors are captured doesn't re-report or re-bill already-covered feedback.
- Every run persists the raw model text, the parsed JSON, the validated report, and the rendered Markdown — a full audit trail, not just the final output.
- Markdown rendering (exhibit names, zone numbers) is done in code from the catalog, not from the model's free text — the model produces structured findings; formatting is deterministic.
- Temperature 0.0, JSON-schema-constrained response format, schema and catalog data treated strictly as data (never as instructions) inside the prompt contract.

This is the part of the system that turns a pile of transcripts into something an organiser can act on without reading every transcript themselves — and the part that took the most engineering care, precisely because it's the part most capable of being confidently wrong.

## The control surface

Two thin front ends, both driving the same in-process `Application` object — neither contains pipeline logic:

- **Terminal** (`src/cli_app.py`): direct in-process calls, Windows keyboard hook (`msvcrt`) for Enter/Esc/Q.
- **Browser** (`ui/`, Next.js): calls the same `Application` over a local-only HTTP API (`src/operator_server.py`, port 8765), proxied through Next.js at `/api/*`. Polls status every 500ms; no logic beyond displaying state and forwarding button presses / keypresses to the API.

An operator can only trigger the actions the engine already exposes — start, accept, discard, stop, generate report. All state ownership, validation, and processing lives in the engine above.

## Architecture at a glance

```
Microphone
   │  PortAudio callback (never blocks)
   ▼
CaptureSession ──bounded queue──▶ Writer thread ──▶ visitor_NNNN.wav (raw, never mutated)
   │
   │  operator accepts (terminal keypress OR browser button — same call underneath)
   ▼
ProcessingQueue (durable, JSON-persisted, self-healing on restart)
   │
   ▼
ProcessingWorker (sequential)
   │  normalize → near-silence/clip check → reject here if invalid (no API cost)
   ▼
Sarvam STT adapter (REST ≤30s / Batch Job API for longer)
   │
   ▼
transcripts/visitor_NNNN.json
   │
   │  operator triggers "Generate report" once capture is stopped and queue is drained
   ▼
Report generation engine: schema-constrained LLM call ──independent validation──▶
   event_feedback_report.md / .json + full audit trail (raw response, parsed JSON, manifest)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full technical breakdown, including the HTTP API reference and the crash-recovery algorithm in detail.

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Audio capture | `sounddevice` (PortAudio), `soundfile` | Low-latency mic I/O, direct WAV streaming to disk |
| Audio processing | `numpy` | DC-offset removal, linear resampling, peak normalization |
| Speech-to-text | Sarvam AI `saaras:v3` (`sarvamai` SDK) | REST for short clips, async batch job for long ones |
| Report generation | Sarvam AI `sarvam-105b` chat completions | JSON-schema-constrained structured output |
| Backend | Python 3.10+, stdlib `http.server` | No framework dependency for the local operator API |
| Operator console (control surface) | Next.js 16, React 19, HeroUI, Tailwind v4, Motion | Local-only web UI, proxies to the Python backend |
| Config | TOML + env vars + CLI flags | Layered override system, no hardcoded paths |
| Tests | `pytest` | State-machine and pipeline tests with a fake STT adapter (no mic, no network) |

## Repository layout

```
src/
  cli_app.py              Terminal control surface: lifecycle, keyboard loop, status render
  operator_server.py      HTTP control surface for the browser console
  config.py                TOML/env/CLI layered configuration
  audio/
    capture.py             Capture engine: PortAudio callback + writer thread
    normalize.py            Resample, peak-normalize, silence/clip detection
  controls/
    keyboard.py             Windows keyboard listener (Enter/Esc/Q)
  pipeline/
    queue.py                 Durable, self-healing FIFO processing queue
    worker_v2.py             Sequential worker: normalize → transcribe → save
  stt/
    sarvam_adapter.py        Sarvam STT client (REST + batch job routing)
    types.py, factory.py, errors.py, audio_duration.py
  reporting/                  The report generation engine (the core deliverable)
    event_report.py          Builds the LLM request, independently validates the response, writes the report
    sarvam_client.py         Sarvam chat-completions HTTP transport
    cli.py                    Standalone CLI: `python -m src.reporting.cli report`
  storage/
    data.py                   Data directory layout, visitor ID allocation

prompts/event_feedback_report_v1.txt   The full evidentiary prompt contract
schemas/event_feedback_report_v1.json  JSON Schema the LLM response must satisfy
context/project_catalog.json           Catalog of exhibit projects the LLM is allowed to reference

ui/                          Browser control surface (proxies to operator_server.py)
tests/                        pytest suite (queue, capture, normalize, worker, report, server)
data/                          Runtime data: audio/, normalized/, quality/, transcripts/, reports/, queue.json
config.toml                    Default configuration
```

## Running it

**1. Install dependencies**

```bash
uv sync --extra dev  # or: pip install -e ".[dev]"
```

**2. Configure**

```bash
cp .env.example .env
# edit .env and set SARVAM_API_KEY (get one at https://dashboard.sarvam.ai)
```

`config.toml` holds the rest of the defaults (sample rate, storage path, silence threshold). Anything in it can be overridden by an environment variable or a CLI flag — see `src/config.py` for the full resolution order.

**3a. Terminal control surface**

```bash
python -m src.cli_app
```

Enter = accept & start next, Esc = discard & retry, Q = stop capture safely (finishes draining the queue first).

**3b. Browser control surface**

```bash
python -m src.operator_server        # engine + API on :8765
cd ui && npm install && npm run dev  # console on :3000
```

**4. Run the report generation engine** (after capture is stopped and the queue has finished draining)

```bash
python -m src.reporting.cli report --data-root data
```

or click **Report** / press **R** in the browser console once it shows "report ready".

## Testing

```bash
pytest
```

The suite covers the queue state machine, crash-recovery from a partial run, the capture writer thread's stop handshake, audio normalization correctness, the report engine's evidence validation (including that raw transcript text never leaks into rendered output, and that already-reported visitors are never re-sent), and the HTTP control surface — all without a real microphone or a live API key, using a fake STT adapter and a fake chat transport.

## Design notes worth knowing

- `silence_threshold_dbfs` and `min_duration_seconds` exist in `config.toml` and `Config` but are not yet wired into `normalize.py`, which currently uses a fixed −50 dBFS near-silence threshold and no minimum-duration check. Flagged here rather than left silent.
- The processing worker is intentionally single-threaded and sequential — one item at a time, FIFO. This trades throughput for simplicity and predictable ordering; correct for a live single-microphone booth.
- The report engine will refuse to run twice on the same feedback: `EventReportError("no unreported completed transcripts found")` is a deliberate guard rail, not a bug.
