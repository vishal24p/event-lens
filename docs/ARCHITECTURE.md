# Architecture

Deep technical reference for every subsystem. Read `README.md` first for the overview.

## 1. Configuration (`src/config.py`)

Layered resolution, lowest to highest priority:

1. Built-in defaults (`default_config()`)
2. `config.toml` (nested `[storage]`, `[audio]`, `[sarvam]` tables get flattened into the `Config` dataclass fields)
3. Environment variables — mapped through the explicit `ENV_VARS` dict (e.g. `TARGET_SAMPLE_RATE` → `target_sample_rate`). Legacy `SARVAM_MODEL` and current `SARVAM_STT_MODEL` both map to the same field, with `SARVAM_STT_MODEL` applied last so it wins if both are set — this keeps old `.env` files working without breaking the newer name.
4. CLI flags (`--data-root`, `--input-device`, etc.)

`Config` is a frozen dataclass; every layer produces a new instance via `dataclasses.replace`-style reconstruction (`_apply_overlay` / `_apply_env`), never mutates in place. `_coerce()` reads the dataclass field's type annotation as a string and converts TOML/env string values to `Path`, `int`, `float`, or `bool` accordingly, including the `X | None` pattern used by `input_device`.

`SARVAM_LLM_MODEL` (the report-generation model) is **not** part of `Config` — it's read directly from `os.environ` in `operator_server.py` and `reporting/cli.py`, since it only matters for the one-shot report step, not the live capture pipeline.

## 2. Audio capture (`src/audio/capture.py`)

The hard constraint: **the PortAudio callback must never block**, or the OS audio driver will glitch/drop frames. `CaptureSession` is built around that constraint:

- `_on_audio()` (the callback) does exactly three things: compute an RMS input level for the UI meter, copy the buffer (PortAudio reuses its internal buffer, so a view would be corrupted), and push it onto a bounded `queue.Queue`. If the queue is full, it drops the oldest block rather than blocking — a same-tradeoff choice as a ring buffer, prioritizing recency over completeness under overload.
- A separate **writer thread** (`_writer_loop`) owns the actual `soundfile.SoundFile` handle and blocks freely on `queue.get()` and disk I/O. It writes PCM_16 WAV directly to a `.partial.wav` file.
- Stopping is a **handshake, not a kill**: `_finalize_locked()` stops the PortAudio stream first (no more callbacks), then keeps retrying to push a `_Stop()` sentinel onto the queue until the writer thread picks it up and exits, then `.join()`s it. This guarantees every already-queued audio block is flushed to disk before the file is closed — no torn WAV files even under queue backpressure.
- `finalize_and_accept()` vs `finalize_and_discard()` share the same stop handshake; the only difference is whether the caller (`Application`) renames the partial to a permanent `visitor_NNNN.wav` or deletes it.
- Sample rate negotiation: prefers 16 kHz, falls back to the input device's native rate if 16 kHz isn't supported — the mismatch is absorbed later at normalization time, not at capture time.

## 3. Keyboard control (`src/controls/keyboard.py`)

Windows-only (`msvcrt.getwch`), runs in its own daemon thread. Maps Enter → `"accept"`, Esc → `"discard"`, Q/q → `"stop"`. Windows special-key sequences arrive as a two-byte prefix (`\x00` or `\xe0`); the listener consumes the second byte and ignores the whole sequence rather than misinterpreting it as a real key. On non-Windows platforms `msvcrt` fails to import, and the listener degrades to a no-op with a stderr warning instead of crashing the app — the web console still works without it.

## 4. Application lifecycle (`src/cli_app.py`)

`Application` is the single state owner shared by both front ends. Key invariants:

- `_action_lock` serializes every capture action (`start_capture`, `accept_current`, `accept_and_pause`, `discard_current`, `stop_capture`) so the keyboard thread and the HTTP server thread can never race on capture state.
- Visitor IDs only advance on **accept**, never on discard — `VisitorIdAllocator.current()` peeks the next ID, `.allocate()` consumes it. Esc re-records into the same ID; Enter commits it and moves on.
- `stop_capture()` is one-way: once `_stop_capture` is set, capture cannot be restarted in the same process run. Any recording in progress is discarded (not accepted) when stop is triggered, since it was never explicitly confirmed by the operator.
- `status_snapshot()`'s `report_ready` flag requires three conditions simultaneously: capture is stopped, the queue has no open work (`pending`/`normalizing`/`transcribing`), and at least one transcript exists that hasn't been included in a previous report yet (`has_unreported_transcripts`). This is what gates the "Generate report" button/keypress in the UI.

## 5. Processing queue (`src/pipeline/queue.py`)

A thread-safe FIFO (`threading.Lock`-guarded list) with five states: `pending → normalizing → transcribing → completed`, or `failed` from any of the first three.

**Persistence**: every mutating call (`enqueue`, `set_status`) rewrites the entire queue as JSON via `_persist_locked()`, using a write-to-temp-file-then-`os.replace()` pattern for atomicity — a crash mid-write can never leave a corrupt `queue.json`.

**Crash recovery** (`_restore()`), run once at startup if a `state_path` is given:

1. Load whatever `queue.json` has. Corrupt or missing → treated as empty, not fatal.
2. For each persisted item, reconcile against the filesystem rather than trusting the stored status blindly:
   - If a transcript file already exists for that visitor → force status to `completed`, regardless of what was last persisted (covers the crash-right-after-writing-transcript-but-before-persisting-status case).
   - Else if it was `pending`/`normalizing`/`transcribing` and the raw WAV still exists → reset to `pending` (re-run normalize+transcribe from scratch; safe because normalize never mutates the raw file and transcription is idempotent).
   - Else if the raw WAV is missing and it wasn't already `failed` → mark `failed` with `"raw wav missing"`.
3. Separately, scan `audio/visitor_*.wav` for any file with no corresponding queue entry at all (covers a crash between accepting a recording and enqueuing it) and add it as `pending` or `completed` based on transcript presence.
4. Persist the reconciled state immediately, so the on-disk file always reflects reality after startup.

This means the worker can be killed at any point — mid-normalize, mid-API-call, mid-write — and restarting the process picks up exactly where it should, without double-transcribing completed work or silently losing accepted recordings.

## 6. Processing worker (`src/pipeline/worker_v2.py`)

Single background thread, strictly sequential — one `QueueItem` at a time, FIFO order preserved (tested explicitly in `test_worker_processes_one_at_a_time`). Loop: `pop_pending()` → if none, sleep on a `threading.Event` (woken by `nudge()` when the capture side enqueues something) → else `_process_one()`.

`_process_one()` steps, each updating queue status so the UI can show live progress:

1. `set_status(NORMALIZING)` → run `normalize_visitor_recording`. If the result status isn't `"valid"` (i.e. it's `near_silence` or `invalid`), mark the item `failed` with the reason and stop — **the item never reaches the STT API**, which is why the real event run shows 5 `"normalization status=near_silence"` failures in `data/queue.json` with zero wasted Sarvam API calls.
2. `set_status(TRANSCRIBING)` → call the STT adapter. Empty/whitespace-only transcript → `failed`, `"transcription returned no text"`.
3. Write `transcripts/visitor_NNNN.json` (visitor ID, both audio file paths, STT provider/model/mode/language, duration, full text, word/segment-level timestamps, status) → `set_status(COMPLETED)`.

Any unhandled exception at any step is caught and recorded as `failed` with `str(e)` — a single bad recording can never crash the worker thread or block the rest of the queue.

The raw WAV is never touched by the worker in any branch, success or failure — normalization always writes to a *separate* file (enforced by an explicit check inside `normalize_visitor_recording` that raw and normalized paths must differ), so the original recording remains recoverable no matter what happens downstream.

## 7. Audio normalization (`src/audio/normalize.py`)

Pure CPU-side signal processing, no external dependency beyond `numpy`/`soundfile`:

- **Peak level (dBFS)**: `20 * log10(max(abs(samples)))`, `-inf` for silence.
- **Clipping**: any sample with `abs(value) >= 1.0` (float32 full-scale).
- **Mono downmix**: pass-through if already mono, else channel-average.
- **DC offset removal**: subtract the mean before resampling, so a biased mic input doesn't bias the resample/normalize steps.
- **Resampling**: linear interpolation (`np.interp` over a time axis built from `np.linspace`) — a deliberately lightweight choice over polyphase/FFT resampling, acceptable given recordings are short spoken-feedback clips, not music.
- **Peak normalization**: scale so the peak sample hits `target_peak_dbfs` (default −3.0 dBFS) exactly, computed as `10^(target_dbfs/20) / peak`.
- **Near-silence detection**: peak *before* normalization ≤ −50 dBFS (constant, not the `silence_threshold_dbfs` config value — see the README design notes).
- **Status**: `"near_silence"` if the near-silence check trips, `"invalid"` if the normalized buffer ended up empty/degenerate, otherwise `"valid"`.

Output: a fresh 16 kHz mono PCM_16 WAV plus a JSON `QualityReport` (before/after peak, clipping flag, silence flag, durations, sample rate/channel conversion record) written next to it. The raw input file is opened read-only and never rewritten.

## 8. Speech-to-text adapter (`src/stt/sarvam_adapter.py`)

Wraps the `sarvamai` SDK behind the `TranscriptionAdapter` protocol (`transcribe(wav_path) -> TranscriptionResult`), so the worker and tests never depend on the Sarvam SDK directly — `tests/conftest.py`'s `FakeAdapter` satisfies the same protocol with zero network calls.

**Routing by duration**: Sarvam's synchronous REST transcription endpoint rejects clips over 30 seconds, so `read_wav_duration_seconds()` checks the file first and routes to one of two paths:

- **REST** (`≤30s`): single blocking call, response mapped straight to a `TranscriptionResult`.
- **Batch Job API** (`>30s`): create job → upload file → start → poll `wait_until_complete()` → download output JSON to a temp directory → parse. Handles the case where the SDK's expected output filename doesn't match by falling back to the job's own output-mapping list.

**Segment reconstruction** (`_segments_from_timestamps`): Sarvam returns either a structured `timestamps` object (word list + start/end arrays) or nothing. The adapter normalizes both the REST response object and the batch JSON payload through the same logic — zip words with start/end times into `Segment` objects when available, degrade to one whole-transcript `Segment` spanning `0.0–0.0` when word-level timestamps aren't present, and return an empty list only when there's no transcript text at all.

## 9. Report generation (`src/reporting/`)

This is the most constrained part of the system — an LLM writing a report that may later be treated as evidence, so the code actively distrusts the model's output.

### Prompt design (`prompts/event_feedback_report_v1.txt`)

Structured as explicit sections read by the model as instructions:

- **`context-contract`**: defines exactly two data sources — `project_catalog` (which projects exist, and how to *identify* which one a visitor means) and `transcripts` (the only source of *experience* claims). If they conflict, the transcript wins for what happened; the catalog only resolves *which* project was meant.
- **`evidence-boundary`**: explicit ban on outside knowledge, invented projects/IDs/visitors, and treating "no feedback" as a negative signal.
- **`analysis-protocol`**: one finding per project maximum, aggregated across every transcript that clearly references it; ambiguous references get folded into the general `event_overview` instead of forced onto a project.
- **`outcome-rules`**: three allowed outcomes — `working_well`, `needs_attention`, `mixed_feedback` (only when the *same* project has both positive and friction evidence) — scoped strictly to this event, never a prediction about future performance.
- **`writing-rules`**: no verbatim quoting, no per-transcript summary, no recommendations, no invented root causes.
- **`final-check`**: a pre-return checklist the model is asked to run against itself (real project IDs, real visitor IDs, no duplicate project findings, valid JSON matching the schema).

### Enforcement (`src/reporting/event_report.py`)

The prompt is a request, not a guarantee — the code verifies independently:

- `sarvam_client.chat()` calls Sarvam's chat-completions endpoint with `response_format: {"type": "json_object"}` and the full JSON Schema appended to the system prompt as a textual instruction, `temperature=0.0` for determinism.
- `_validate_narrative()` re-checks the parsed response against ground truth the model doesn't get to redefine: `event_overview` and `report_limitations` are non-empty strings; every finding's `project_id` must exist in the *actual* catalog passed in; every `outcome` must be one of the three allowed values; every `supporting_visitor_ids` entry must be a real visitor ID from the *actual* transcript set for this run; no project ID appears twice. Any violation raises `EventReportError` and no report file is written.
- **Incremental reporting**: `manifest.json` in `data/reports/` tracks which visitor IDs have already been included in a previous report (`_reported_visitor_ids`). Each new report run only sends *unreported* transcripts to the LLM (`_read_transcripts(..., excluded_visitor_ids=...)`) — running the report command again after more visitors are captured doesn't re-report or re-bill for feedback already covered.
- **Full audit trail**: every run writes the raw LLM text (`{report_id}.response.txt`), the parsed JSON (`{report_id}.response.json`), the validated final report (`{report_id}.json`), and the rendered Markdown (`{report_id}.md`, plus a rolling `event_feedback_report.md` that always points at the latest), all via atomic temp-file-then-`replace()` writes.
- `_markdown()` renders the validated report deterministically in code — grouped by outcome (`Working well` / `Needs attention` / `Mixed feedback`), each finding tagged with the project's display name and zone number pulled from the catalog, not from the model's free text.

### Transport (`src/reporting/sarvam_client.py`)

Zero third-party HTTP dependency — raw `urllib.request`. Maps Sarvam's HTTP failure modes to typed exceptions the caller can branch on: `SarvamAuthError` (401/403), `SarvamRateLimitError` (429, carries `Retry-After` if present), `SarvamServerError` (5xx and connection-level `URLError`), `SarvamSchemaError` (200 response but content isn't valid JSON, or isn't a JSON object). `generate_event_report()` accepts an injectable `transport` callable purely for testing — production always uses `sarvam_client.chat`.

### Standalone CLI (`src/reporting/cli.py`)

`python -m src.reporting.cli report --data-root data` — the same code path the web console's **Report** button calls, but runnable independently (e.g. after the event, on a different machine, from a backed-up `data/` folder). Deliberately hardcodes acceptance of only `sarvam-105b` as a guard rail against silently pointing report generation at an unvalidated model.

## 10. Local operator HTTP API (`src/operator_server.py`)

Stdlib `ThreadingHTTPServer`, bound to `127.0.0.1` only — never exposed beyond localhost, since it controls a live microphone.

| Method | Path | Action | Failure mode |
|---|---|---|---|
| GET | `/api/status` | `Application.status_snapshot()` | — |
| GET | `/api/report/markdown` | Serve the latest `event_feedback_report.md` | `404 report_not_found` |
| POST | `/api/capture/start` | `start_capture()` | `409 invalid_capture_state` |
| POST | `/api/capture/accept` | `accept_current()` | `409 invalid_capture_state` |
| POST | `/api/capture/accept-and-pause` | `accept_and_pause()` | `409 invalid_capture_state` |
| POST | `/api/capture/discard` | `discard_current()` | `409 invalid_capture_state` |
| POST | `/api/capture/stop` | `stop_capture()` | `409 invalid_capture_state` |
| POST | `/api/report` | Generate the event report | `409 report_not_ready` if capture isn't stopped/queue isn't drained/no new transcripts; `500 report_failed` on provider/network error |

Every `RuntimeError` raised by `Application` (invalid state transitions like accepting with nothing recording) is caught at the handler level and turned into a `409` with a structured `{"error": {"code", "message"}}` body — the frontend never has to guess why an action failed.

## 11. Operator console (`ui/`)

Next.js 16 / React 19, client-rendered (`"use client"`), polls `GET /api/status` every 500ms rather than using a push channel — simple and sufficient for a single local operator. `next.config.mjs` rewrites `/api/:path*` to `http://127.0.0.1:8765/api/:path*`, so the browser only ever talks to its own origin; the Python server does not need CORS handling.

Keyboard shortcuts are re-implemented in the browser (`Enter`/`Esc`/`Q`/`R`/`?`) independently of the Python `msvcrt` listener — the two front ends are alternatives, not layered on top of each other. Button `disabled` state and the keyboard handler both gate on the same `status.capture_state` value from the last poll, so the UI can't fire an action it already knows the backend will reject.

## 12. Testing strategy (`tests/`)

- **No real hardware or network in the default suite.** `FakeAdapter` (in `conftest.py`) satisfies `TranscriptionAdapter` and lets `test_capture_state_machine.py` exercise the full normalize → transcribe → complete/fail pipeline deterministically, including forcing a failure for a specific visitor ID to assert the raw WAV survives untouched.
- **State-machine focus, not just happy path**: FIFO ordering under concurrent-looking load, non-pending items rejected from `enqueue`, failed items not blocking `has_open_work`, allocator advancing only on accept.
- **Crash recovery is directly tested** (`test_durable_queue_recovers_interrupted_work_without_retranscribing_completed`): pre-seed a transcript for one visitor, mark both visitors `transcribing` in a fresh queue, reload from disk, assert the transcript-having visitor comes back `completed` and the other comes back `pending`.
- **Report validation is tested against both the happy path and the guard rails** (`test_event_report.py`): confirms the exact transcript text and catalog reach the model call, confirms raw visitor text/IDs never leak into the rendered Markdown, confirms a second report run with no new transcripts raises instead of silently re-sending.
- **HTTP layer tested against a fake `Application`** (`test_operator_server.py`), so server routing/status-code behavior is verified independently of real capture logic; capture internals (`_on_audio`, writer thread stop handshake) are tested by calling private methods directly where no public seam exists yet.
