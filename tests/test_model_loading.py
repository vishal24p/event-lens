"""Model loading rules: no download, no CPU fallback, clear errors."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from src.models import transcribe as t


def test_missing_model_path_prints_user_command(monkeypatch, tmp_path):
    # Force CUDA check to pass via ctranslate2.
    fake_ct2 = mock.MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    missing = tmp_path / "nope"
    with pytest.raises(t.ModelMissingError) as exc:
        t.FasterWhisperAdapter(missing)
    msg = str(exc.value)
    assert "uv add huggingface_hub" in msg
    assert "uv run hf download" in msg
    assert "Systran/faster-whisper-small" in msg


def test_incomplete_model_dir_raises(monkeypatch, tmp_path):
    fake_ct2 = mock.MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    partial = tmp_path / "models"
    partial.mkdir()
    # No .bin, no tokenizer, no config.
    with pytest.raises(t.ModelMissingError):
        t.FasterWhisperAdapter(partial)


def test_cuda_unavailable_raises(monkeypatch, tmp_path):
    fake_ct2 = mock.MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 0
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    with pytest.raises(t.CudaUnavailableError) as exc:
        t.FasterWhisperAdapter(tmp_path / "whatever")
    assert "CUDA GPU unavailable" in str(exc.value)
    assert "CPU fallback is disabled" in str(exc.value)


def test_adapter_passes_local_path(monkeypatch, tmp_path):
    """Verify the adapter passes a local path - never a size string."""
    captured = {}

    class _FakeWhisperModel:
        def __init__(self, model_path_or_size, device, compute_type):
            captured["path"] = model_path_or_size
            captured["device"] = device
            captured["compute_type"] = compute_type
            captured["is_str_size"] = model_path_or_size in ("tiny", "base", "small", "medium", "large-v3")

        def transcribe(self, *a, **kw):
            return iter([]), mock.MagicMock(language="en")

    fake_ct2 = mock.MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2)
    fake_mod = mock.MagicMock()
    fake_mod.WhisperModel = _FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)

    model_dir = tmp_path / "models" / "faster-whisper-small"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"x")
    (model_dir / "tokenizer.json").write_text("{}")
    (model_dir / "config.json").write_text("{}")

    t.FasterWhisperAdapter(model_dir)
    assert captured["is_str_size"] is False
    assert captured["device"] == "cuda"
    assert captured["compute_type"] == "float16"
    assert Path(captured["path"]) == model_dir
