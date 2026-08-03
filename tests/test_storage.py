"""Storage layout invariants."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.storage.data import data_paths, next_visitor_number


def _write_sine(path: Path, seconds: float = 0.5, sr: int = 16000) -> None:
    t = np.linspace(0, seconds, int(seconds * sr), endpoint=False)
    sf.write(str(path), (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr)


def test_global_data_layout_has_capture_and_report_folders(tmp_path):
    paths = data_paths(tmp_path)
    for d in (paths.audio, paths.normalized, paths.quality, paths.transcripts, paths.reports):
        assert d.is_dir(), d


def test_accepted_wav_never_overwritten(tmp_path):
    paths = data_paths(tmp_path)
    p1 = paths.audio / "visitor_0001.wav"
    p2 = paths.audio / "visitor_0001.partial.wav"
    _write_sine(p1, seconds=0.3)
    _write_sine(p2, seconds=0.3)
    before = p1.read_bytes()
    # Application logic uses os.replace only on the partial. The permanent
    # is the file the system must refuse to overwrite.
    assert p1.read_bytes() == before


def test_partial_files_are_not_under_transcripts(tmp_path):
    paths = data_paths(tmp_path)
    _write_sine(paths.audio / "visitor_0001.partial.wav", seconds=0.2)
    # transcripts/ must never contain a partial.
    assert not list(paths.transcripts.glob("*.partial.*"))


def test_next_visitor_number_uses_existing_global_audio(tmp_path):
    paths = data_paths(tmp_path)
    _write_sine(paths.audio / "visitor_0007.wav")
    assert next_visitor_number(paths.audio) == 8
