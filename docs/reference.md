# Event Lens reference

This reference describes the externally configurable and observable surface of Event Lens.

## Python commands

### `event-lens`

Runs the terminal capture application.

```text
event-lens [--config PATH] [--data-root PATH] [--input-device INTEGER] [--check-only]
```

| Option | Default | Effect |
| --- | --- | --- |
| `--config` | `config.toml` | TOML configuration file. A missing file is treated as no TOML override. |
| `--data-root` | Resolved configuration value | Root for accepted audio, derived audio, queue state, transcripts, and reports. |
| `--input-device` | Resolved configuration value | Numeric input-device index passed to the audio backend. |
| `--check-only` | Off | Resolves configuration and prints the transcription provider, model, and mode without starting capture. |

The terminal application supports Enter to accept, Escape to discard, and Q to stop. Its keyboard listener uses Windows `msvcrt`; non-Windows terminals continue without those keyboard controls.

### `python -m src.operator_server`

Starts the local HTTP API used by the browser console.

```text
python -m src.operator_server [--config PATH] [--data-root PATH] [--input-device INTEGER] [--port INTEGER]
```

`--port` defaults to `8765`. The server binds to `127.0.0.1`, not a network interface.

### `python -m src.reporting.cli report`

Builds an event report from unreported completed transcripts.

```text
python -m src.reporting.cli report [--data-root PATH] [--model sarvam-105b]
```

`--data-root` defaults to `data`. `--model` is restricted to `sarvam-105b`; a missing API key returns exit code 3, a bad data path or model returns 2, and report or provider failures return 1.

## Configuration

Values resolve in this order, with later sources winning: built-in defaults, TOML, environment variables, then supported CLI flags.

| TOML key | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `storage.data_root` | `DATA_ROOT` | `data` | Root for application outputs. |
| `storage.input_device` | `INPUT_DEVICE` | system default | Input-device index. |
| `audio.target_sample_rate` | `TARGET_SAMPLE_RATE` | `16000` | Preferred capture and normalized output rate. A device may capture at its native rate and be resampled later. |
| `audio.channels` | `CHANNELS` | `1` | Capture channel count. |
| `audio.block_size` | `BLOCK_SIZE` | `4000` | Frames per audio callback. |
| `audio.audio_queue_blocks` | `AUDIO_QUEUE_BLOCKS` | `64` | Maximum callback-to-writer audio blocks. |
| `audio.peak_target_dbfs` | `PEAK_TARGET_DBFS` | `-3.0` | Peak-normalization target. |
| `audio.silence_threshold_dbfs` | `SILENCE_THRESHOLD_DBFS` | `-50.0` | Exposed silence threshold. The current normalizer uses a fixed `-50.0` dBFS threshold. |
| `audio.min_duration_seconds` | `MIN_DURATION_SECONDS` | `0.5` | Exposed minimum duration. The current capture path does not enforce it. |
| `sarvam.api_key` | `SARVAM_API_KEY` | empty | Required Sarvam API key. |
| `sarvam.model` | `SARVAM_STT_MODEL` | `saaras:v3` | Speech-to-text model. `SARVAM_MODEL` is accepted as a lower-priority legacy alias. |
| `sarvam.mode` | `SARVAM_MODE` | `codemix` | Sarvam transcription mode. |
| `sarvam.language_code` | `SARVAM_LANGUAGE_CODE` | `unknown` | Language code; `unknown` enables automatic detection. |

`SARVAM_LLM_MODEL` controls the report service's requested model and defaults to `sarvam-105b`. The standalone report CLI rejects any other model.

## Local HTTP API

All JSON responses use either `{ "data": ... }` or `{ "error": { "code": string, "message": string } }`.

| Method and path | Success | Behavior |
| --- | --- | --- |
| `GET /api/status` | 200 | Returns capture state, active visitor, elapsed seconds, RMS input level, queue counts and items, and `report_ready`. |
| `POST /api/capture/start` | 200 | Starts the next recording from the idle state. |
| `POST /api/capture/accept` | 200 | Accepts the active recording and immediately starts the next one. |
| `POST /api/capture/accept-and-pause` | 200 | Accepts the active recording and returns to idle. |
| `POST /api/capture/discard` | 200 | Deletes the active partial recording and starts the same visitor ID again. |
| `POST /api/capture/stop` | 200 | Stops recording, discards the partial WAV, and drains accepted work. |
| `POST /api/report` | 200 | Generates a report if it is ready; returns `markdown_url` and the actual model. |
| `GET /api/report/markdown` | 200 | Returns the latest report as Markdown. |

Invalid capture transitions return 409 with `invalid_capture_state`. A report requested before it is ready returns 409 with `report_not_ready`; a missing report Markdown file returns 404 with `report_not_found`.

## Generated records

For each accepted visitor, the configured data root receives a raw WAV, a normalized mono 16 kHz WAV, a quality JSON record, and, on successful transcription, a transcript JSON record. The raw accepted WAV is never modified or deleted by the processing worker.

Queue state is stored as `queue.json`. Each item records its visitor ID, raw-audio filename, status, and optional error. Valid statuses are `pending`, `normalizing`, `transcribing`, `completed`, and `failed`. On restart, existing transcripts mark their records completed; recoverable in-flight work with a raw WAV returns to pending.

A transcript contains the visitor ID, relative raw and normalized audio references, Sarvam settings, detected language, duration, text, timestamped segments, and a `completed` status.

Each report run stores the provider response, a versioned JSON report, timestamped Markdown, the latest Markdown alias `event_feedback_report.md`, and a manifest. The manifest prevents the same completed transcripts from being reported twice. Report Markdown groups validated findings into working well, needs attention, and mixed feedback; it excludes raw transcripts and supporting visitor IDs.
