"""Simple CPU-side normalization and validation.

Produces a separate normalized 16 kHz mono WAV and a quality metadata JSON.
Never modifies the accepted raw WAV.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf


_NEAR_SILENCE_PEAK_DBFS = -50.0
_CLIP_SAMPLE_VALUE = 1.0  # float32 sample clipping threshold


@dataclass
class QualityReport:
    visitor_id: str
    original_sample_rate: int
    output_sample_rate: int
    original_channels: int
    output_channels: int
    duration_seconds: float
    peak_before_dbfs: float
    peak_after_dbfs: float
    clipping_detected: bool
    near_silence_detected: bool
    status: str  # "valid" | "near_silence" | "invalid"


def _peak_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return float("-inf")
    peak = float(np.max(np.abs(samples)))
    if peak <= 0.0:
        return float("-inf")
    return 20.0 * math.log10(peak)


def _has_clipping(samples: np.ndarray) -> bool:
    if samples.size == 0:
        return False
    return bool(np.any(np.abs(samples) >= _CLIP_SAMPLE_VALUE))


def _to_mono(samples: np.ndarray) -> np.ndarray:
    if samples.ndim == 1:
        return samples
    if samples.shape[1] == 1:
        return samples[:, 0]
    return np.mean(samples, axis=1)


def _resample_linear(samples: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return samples
    # Lightweight polyphase resampling via numpy. Acceptable for short recordings.
    duration = samples.shape[0] / float(sr_in)
    n_out = int(round(duration * sr_out))
    if n_out <= 0:
        return np.zeros(0, dtype=samples.dtype)
    x_old = np.linspace(0.0, duration, num=samples.shape[0], endpoint=False)
    x_new = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(samples.dtype, copy=False)


def _peak_normalize(samples: np.ndarray, target_dbfs: float) -> np.ndarray:
    if samples.size == 0:
        return samples
    peak = float(np.max(np.abs(samples)))
    if peak <= 0.0:
        return samples
    target_linear = 10.0 ** (target_dbfs / 20.0)
    gain = target_linear / peak
    return (samples * gain).astype(np.float32, copy=False)


def normalize_visitor_recording(
    *,
    visitor_id: str,
    raw_path: Path,
    normalized_path: Path,
    quality_path: Path,
    target_sample_rate: int,
    target_peak_dbfs: float,
) -> QualityReport:
    """Read raw WAV, write normalized WAV + quality JSON. Raw is untouched."""
    if not raw_path.exists():
        raise FileNotFoundError(f"raw wav missing: {raw_path}")
    if raw_path.resolve() == normalized_path.resolve():
        raise ValueError("normalized_path must differ from raw_path")

    with sf.SoundFile(str(raw_path), mode="r") as f:
        sr_in = int(f.samplerate)
        ch_in = int(f.channels)
        subtype_in = f.subtype
        # Read the whole file into a float32 array. Short recordings => fine.
        samples = f.read(dtype="float32", always_2d=True)

    peak_before = _peak_dbfs(samples)
    clipping = _has_clipping(samples)
    mono = _to_mono(samples)
    dc_removed = mono - float(np.mean(mono)) if mono.size else mono
    resampled = _resample_linear(dc_removed, sr_in, target_sample_rate)
    normalized = _peak_normalize(resampled, target_peak_dbfs)
    peak_after = _peak_dbfs(normalized)
    near_silence = peak_before <= _NEAR_SILENCE_PEAK_DBFS

    if near_silence:
        status = "near_silence"
    elif normalized.size == 0 or peak_after == float("-inf"):
        status = "invalid"
    else:
        status = "valid"

    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    with sf.SoundFile(
        str(normalized_path),
        mode="w",
        samplerate=target_sample_rate,
        channels=1,
        subtype="PCM_16",
    ) as out:
        out.write(normalized.astype(np.float32, copy=False))

    duration = normalized.shape[0] / float(target_sample_rate) if normalized.size else 0.0

    report = QualityReport(
        visitor_id=visitor_id,
        original_sample_rate=sr_in,
        output_sample_rate=target_sample_rate,
        original_channels=ch_in,
        output_channels=1,
        duration_seconds=round(duration, 3),
        peak_before_dbfs=round(peak_before, 2)
        if peak_before != float("-inf")
        else float("-inf"),
        peak_after_dbfs=round(peak_after, 2)
        if peak_after != float("-inf")
        else float("-inf"),
        clipping_detected=clipping,
        near_silence_detected=near_silence,
        status=status,
    )
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    quality_path.write_text(
        json.dumps(report.__dict__, indent=2), encoding="utf-8"
    )
    return report
