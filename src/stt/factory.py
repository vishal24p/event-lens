"""Build the configured STT adapter."""
from __future__ import annotations

from .sarvam_adapter import SarvamTranscriptionAdapter
from .types import TranscriptionAdapter


def build_default_adapter(
    *,
    api_key: str | None = None,
    model: str = "saaras:v3",
    mode: str = "codemix",
    language_code: str = "unknown",
) -> TranscriptionAdapter:
    return SarvamTranscriptionAdapter(
        api_key=api_key,
        model=model,
        mode=mode,
        language_code=language_code,
    )
