"""Sarvam AI Saaras v3 transcription adapter.

Uses the REST API for clips up to 30 seconds and the batch job API for
longer normalized visitor recordings.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, List

from .audio_duration import read_wav_duration_seconds
from .errors import SarvamApiKeyMissingError
from .types import Segment, TranscriptionResult

# Sarvam REST transcribe rejects audio longer than 30 seconds.
REST_MAX_DURATION_SECONDS = 30.0

SARVAM_API_KEY_HELP = (
    "Sarvam API key missing.\n"
    "Set SARVAM_API_KEY in your environment or in a .env file.\n"
    "Get a key at https://dashboard.sarvam.ai"
)


class SarvamTranscriptionAdapter:
    """Adapter around Sarvam AI speech-to-text (saaras:v3)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "saaras:v3",
        mode: str = "codemix",
        language_code: str = "unknown",
    ) -> None:
        resolved_key = (api_key or os.environ.get("SARVAM_API_KEY") or "").strip()
        if not resolved_key:
            raise SarvamApiKeyMissingError(SARVAM_API_KEY_HELP)
        from sarvamai import SarvamAI

        self._client = SarvamAI(api_subscription_key=resolved_key)
        self._model = model
        self._mode = mode
        self._language_code = language_code

    def transcribe(
        self, wav_path: Path, initial_prompt: str = ""
    ) -> TranscriptionResult:
        del initial_prompt  # Sarvam uses mode (e.g. codemix) instead of prompts.
        duration = read_wav_duration_seconds(wav_path)
        if duration <= REST_MAX_DURATION_SECONDS:
            return self._transcribe_rest(wav_path)
        return self._transcribe_batch(wav_path)

    def _transcribe_rest(self, wav_path: Path) -> TranscriptionResult:
        with wav_path.open("rb") as handle:
            response = self._client.speech_to_text.transcribe(
                file=handle,
                model=self._model,
                mode=self._mode,
                language_code=self._language_code,
                input_audio_codec="wav",
            )
        return _response_to_result(response)

    def _transcribe_batch(self, wav_path: Path) -> TranscriptionResult:
        job = self._client.speech_to_text_job.create_job(
            model=self._model,
            mode=self._mode,
            language_code=self._language_code,
            with_timestamps=True,
        )
        job.upload_files(file_paths=[str(wav_path)])
        status = job.start()
        if status.job_state.lower() == "failed":
            raise RuntimeError(f"Sarvam batch job failed to start: {status}")
        status = job.wait_until_complete()
        if status.job_state.lower() != "completed":
            raise RuntimeError(f"Sarvam batch job did not complete: {status.job_state}")

        with tempfile.TemporaryDirectory(prefix="sarvam-stt-") as tmp:
            job.download_outputs(output_dir=tmp)
            result_path = Path(tmp) / f"{wav_path.name}.json"
            if not result_path.exists():
                mappings = job.get_output_mappings()
                if not mappings:
                    raise RuntimeError("Sarvam batch job returned no output files")
                result_path = Path(tmp) / mappings[0]["output_file"]
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        return _payload_to_result(payload)


def _response_to_result(response: Any) -> TranscriptionResult:
    transcript = str(getattr(response, "transcript", "") or "").strip()
    language = str(getattr(response, "language_code", None) or "unknown")
    segments = _segments_from_timestamps(getattr(response, "timestamps", None), transcript)
    return TranscriptionResult(language=language, text=transcript, segments=segments)


def _payload_to_result(payload: dict[str, Any]) -> TranscriptionResult:
    transcript = str(payload.get("transcript") or payload.get("text") or "").strip()
    language = str(payload.get("language_code") or "unknown")
    timestamps = payload.get("timestamps")
    segments = _segments_from_timestamps(timestamps, transcript)
    return TranscriptionResult(language=language, text=transcript, segments=segments)


def _segments_from_timestamps(timestamps: Any, transcript: str) -> List[Segment]:
    if timestamps is None:
        if not transcript:
            return []
        return [Segment(start=0.0, end=0.0, text=transcript)]

    if isinstance(timestamps, dict):
        words = timestamps.get("words") or []
        starts = timestamps.get("start_time_seconds") or []
        ends = timestamps.get("end_time_seconds") or []
    else:
        words = getattr(timestamps, "words", None) or []
        starts = getattr(timestamps, "start_time_seconds", None) or []
        ends = getattr(timestamps, "end_time_seconds", None) or []

    if not words:
        if not transcript:
            return []
        return [Segment(start=0.0, end=0.0, text=transcript)]

    segments: List[Segment] = []
    for word, start, end in zip(words, starts, ends):
        text = str(word).strip()
        if text:
            segments.append(Segment(start=float(start), end=float(end), text=text))
    if segments:
        return segments
    if transcript:
        return [Segment(start=0.0, end=0.0, text=transcript)]
    return []
