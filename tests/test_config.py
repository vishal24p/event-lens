"""Configuration environment-variable coverage."""
from __future__ import annotations

from src.config import load_config


def test_explicit_stt_model_environment_variable_wins_over_legacy_name(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SARVAM_MODEL", "legacy-stt-model")
    monkeypatch.setenv("SARVAM_STT_MODEL", "configured-stt-model")

    config = load_config(config_path=tmp_path / "missing.toml")

    assert config.sarvam_model == "configured-stt-model"
