"""Configuration environment-variable coverage."""
from __future__ import annotations

from pathlib import Path

from src.config import load_config


def test_explicit_stt_model_environment_variable_wins_over_legacy_name(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SARVAM_MODEL", "legacy-stt-model")
    monkeypatch.setenv("SARVAM_STT_MODEL", "configured-stt-model")

    config = load_config(config_path=tmp_path / "missing.toml")

    assert config.sarvam_model == "configured-stt-model"


def test_data_root_environment_variable_is_a_path(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", "event-data")

    config = load_config(config_path=tmp_path / "missing.toml")

    assert config.data_root == Path("event-data")
