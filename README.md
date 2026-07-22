# Feedback-LLM — Phase 1

Operator-controlled audio feedback capture with local faster-whisper
transcription. Single visitor at a time. Manual accept / discard / stop.

## Phase 1 scope

- One microphone, one visitor at a time.
- Operator keys: `ENTER` accept, `ESC` discard current, `Q` stop capture.
- Sequential processing queue. One Whisper inference at a time.
- Local faster-whisper `small` model only. No model download by the app.
- No diarization, no streaming, no LLM, no frontend, no SQLite.

## 1. Install

```bash
uv sync
```

## 2. Download the model (you run this once, the app never does)

The model is configured in `config.toml`. Default is `medium`. To use a
different size, change `[model].model_size` and download that model:

```bash
uv run hf download Systran/faster-whisper-medium --local-dir models/faster-whisper-medium
```

For a smaller model:

```bash
uv run hf download Systran/faster-whisper-small --local-dir models/faster-whisper-small
# then edit config.toml:
#   [model]
#   model_path = "models/faster-whisper-small"
#   model_size = "small"
```

Confirm the folder contains at least `model.bin`, `config.json`, and a
tokenizer file (`tokenizer.json` or `tokenizer.model`).

## 3. Validate configuration

```bash
uv run feedback-llm --check-only
```

Exits non-zero if CUDA is missing or the model directory is incomplete. Prints
the effective model path, size, device, and compute type.

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
