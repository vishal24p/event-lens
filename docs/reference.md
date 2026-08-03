# Reference

This page describes the commands, configuration, local API, and stored records used by Event Lens.

## Commands

### `event-lens`

Runs the terminal capture application.

```text
event-lens [--config PATH] [--data-root PATH] [--input-device INTEGER] [--check-only]
```

| Option | Meaning |
| --- | --- |
| `--config` | TOML configuration file. Default: `config.toml`. |
| `--data-root` | Root directory for accepted audio, derived files, queue state, transcripts, and reports. |
| `--input-device` | Numeric recording-device index. List available devices with `uv run python -c "import sounddevice as sd; print(sd.query_devices())"`; use an input device, not an output device. |
| `--check-only` | Prints resolved transcription settings without starting capture. |

### `python -m src.operator_server`

Starts the local API used by the browser console.

```text
python -m src.operator_server [--config PATH] [--data-root PATH] [--input-device INTEGER] [--port INTEGER]
```

The default port is `8765`. The server listens only on `127.0.0.1`.

### `python -m src.reporting.cli report`

Creates an event feedback report from completed transcripts that have not already been reported.

```text
python -m src.reporting.cli report [--data-root PATH] [--model sarvam-105b]
```

The data root defaults to `data`. The report model is currently restricted to `sarvam-105b`.

## Configuration

Configuration values are resolved in this order: built-in defaults, `config.toml`, environment variables, then supported command-line flags.

| TOML key | Environment variable | Default | Purpose |
| --- | --- | --- | --- |
| `storage.data_root` | `DATA_ROOT` | `data` | Root for application output. |
| `storage.input_device` | `INPUT_DEVICE` | system default | Input-device index. Set this for a fixed external microphone; omit it to use the system default, such as the laptop microphone. |
| `audio.target_sample_rate` | `TARGET_SAMPLE_RATE` | `16000` | Preferred capture and normalised output rate. |
| `audio.channels` | `CHANNELS` | `1` | Capture channel count. |
| `audio.block_size` | `BLOCK_SIZE` | `4000` | Frames per callback. |
| `audio.audio_queue_blocks` | `AUDIO_QUEUE_BLOCKS` | `64` | Maximum capture-to-writer blocks. |
| `audio.peak_target_dbfs` | `PEAK_TARGET_DBFS` | `-3.0` | Peak-normalisation target. |
| `audio.silence_threshold_dbfs` | `SILENCE_THRESHOLD_DBFS` | `-50.0` | Reserved compatibility setting; the normaliser currently uses `-50.0` dBFS. |
| `audio.min_duration_seconds` | `MIN_DURATION_SECONDS` | `0.5` | Reserved compatibility setting; the capture path does not currently enforce it. |
| `sarvam.api_key` | `SARVAM_API_KEY` | empty | Required Sarvam API key. |
| `sarvam.model` | `SARVAM_STT_MODEL` | `saaras:v3` | Speech-to-text model. |
| `sarvam.mode` | `SARVAM_MODE` | `codemix` | Transcription mode. |
| `sarvam.language_code` | `SARVAM_LANGUAGE_CODE` | `unknown` | Language code; `unknown` enables detection. |

`SARVAM_LLM_MODEL` selects the report model and defaults to `sarvam-105b`.

## Local API

Every JSON response is either `{ "data": ... }` or `{ "error": { "code": string, "message": string } }`.

| Route | Purpose |
| --- | --- |
| `GET /api/status` | Current capture state, active visitor, input level, queue state, and report availability. |
| `POST /api/capture/start` | Starts the next recording. |
| `POST /api/capture/accept` | Saves the active recording and starts the next one. |
| `POST /api/capture/accept-and-pause` | Saves the active recording and returns to ready. |
| `POST /api/capture/discard` | Discards the active partial recording and restarts the same visitor ID. |
| `POST /api/capture/stop` | Stops capture, discards the active partial WAV, and lets accepted work finish. |
| `POST /api/report` | Generates the report when it is ready. |
| `GET /api/report/markdown` | Returns the latest event feedback report as Markdown. |

Invalid capture actions return HTTP 409. Requesting a report before it is ready also returns HTTP 409.

## Stored data

The configured data root contains:

| Path | Contents |
| --- | --- |
| `audio/` | Original accepted WAV files. |
| `normalized/` | Derived mono 16 kHz WAV files. |
| `quality/` | Audio-quality records. |
| `transcripts/` | Completed transcript JSON files. |
| `queue.json` | Durable processing state. |
| `reports/` | Provider responses, versioned report JSON and Markdown, `event_feedback_report.md`, and the report manifest. |

Each queue item has one of these statuses: `pending`, `normalizing`, `transcribing`, `completed`, or `failed`. The report manifest prevents a completed transcript from being included in more than one report.
