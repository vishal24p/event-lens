"""Speech-to-text adapters (Sarvam AI Saaras v3)."""

from .factory import build_default_adapter
from .types import Segment, TranscriptionAdapter, TranscriptionResult

__all__ = [
    "Segment",
    "TranscriptionAdapter",
    "TranscriptionResult",
    "build_default_adapter",
]
