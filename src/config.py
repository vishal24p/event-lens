"""Configuration: TOML file + env var overlay, no hardcoded paths in modules.

Resolution order (lowest priority first):
  1. Built-in defaults.
  2. TOML config file (default: ./config.toml, override via --config PATH).
  3. Environment variables (unprefixed, e.g. MODEL_SIZE, MODEL_PATH).
  4. CLI flags (highest priority, where present).

Env var mapping is documented below. None of these are required; sensible
defaults are baked in.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict


# Env var -> Config field name. Add new entries here when extending Config.
ENV_VARS: Dict[str, str] = {
    "MODEL_PATH": "model_path",
    "MODEL_SIZE": "model_size",
    "SESSIONS_ROOT": "sessions_root",
    "INPUT_DEVICE": "input_device",
    "TARGET_SAMPLE_RATE": "target_sample_rate",
    "CHANNELS": "channels",
    "BLOCK_SIZE": "block_size",
    "AUDIO_QUEUE_BLOCKS": "audio_queue_blocks",
    "PEAK_TARGET_DBFS": "peak_target_dbfs",
    "SILENCE_THRESHOLD_DBFS": "silence_threshold_dbfs",
    "MIN_DURATION_SECONDS": "min_duration_seconds",
    "DEVICE": "device",
    "COMPUTE_TYPE": "compute_type",
    "INITIAL_PROMPT": "initial_prompt",
}


@dataclass(frozen=True)
class Config:
    # Path to the pre-downloaded faster-whisper model directory.
    model_path: Path
    # Logical model name (e.g. "small", "medium", "large-v3"). Used for the
    # transcript metadata only; the loader always uses model_path on disk.
    model_size: str

    # Root directory under which session folders are created.
    sessions_root: Path

    # Audio capture device index. None = default input device.
    input_device: int | None

    # Preferred capture sample rate. Used when the device supports it.
    # Otherwise the device's native rate is used and resampled at normalize time.
    target_sample_rate: int = 16_000

    # Capture channels. Always mono at capture time.
    channels: int = 1

    # Audio block size in frames passed to the PortAudio callback.
    block_size: int = 4_000

    # Bounded queue size (audio blocks) between callback and writer thread.
    audio_queue_blocks: int = 64

    # Peak normalization target in dBFS.
    peak_target_dbfs: float = -3.0

    # Near-silence detection threshold in dBFS.
    silence_threshold_dbfs: float = -50.0

    # Minimum recording duration in seconds; below this, recording is rejected.
    min_duration_seconds: float = 0.5

    # Inference device. Always "cuda" for Phase 1; "cpu" is explicitly disabled
    # in transcribe.py but kept here for completeness of the config schema.
    device: str = "cuda"

    # CTranslate2 compute type. "float16" is the standard choice on consumer
    # NVIDIA GPUs. Other valid values: "int8", "int8_float16", "float32".
    compute_type: str = "float16"

    # Optional initial prompt passed to Whisper. Useful for code-switched
    # audio (e.g. "Tamil and English") to bias the decoder toward the
    # expected script and vocabulary. Leave empty for default behaviour.
    initial_prompt: str = ""


def _load_toml(path: Path) -> Dict[str, Any]:
    """Read a TOML config file. Returns {} if missing."""
    if not path.exists():
        return {}
    if sys.version_info >= (3, 11):
        import tomllib  # type: ignore[import-not-found]

        with path.open("rb") as f:
            return tomllib.load(f)
    import tomli  # type: ignore[import-not-found]

    with path.open("rb") as f:
        return tomli.load(f)


def _coerce(field_name: str, value: Any) -> Any:
    """Coerce an env/TOML value to the type declared on Config."""
    for f in fields(Config):
        if f.name == field_name:
            t = f.type
            if t == "Path" or t == "str" or t.startswith("str"):
                return value
            if t == "int" or t.startswith("int"):
                return int(value)
            if t == "float" or t.startswith("float"):
                return float(value)
            if t == "bool" or t.startswith("bool"):
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("1", "true", "yes", "on")
            if t.endswith("| None"):
                if value in ("", "None", "none"):
                    return None
                return int(value) if "int" in t else value
            return value
    return value


def default_config() -> Config:
    return Config(
        model_path=Path("models") / "faster-whisper-medium",
        model_size="medium",
        sessions_root=Path("sessions"),
        input_device=None,
    )


def load_config(
    *,
    config_path: Path | None = None,
    cli_overrides: Dict[str, Any] | None = None,
) -> Config:
    """Build a Config from defaults < TOML < env < CLI overrides."""
    cfg = default_config()
    toml_data = _load_toml(config_path or Path("config.toml"))
    if toml_data:
        cfg = _apply_overlay(cfg, toml_data)
    cfg = _apply_env(cfg)
    if cli_overrides:
        cfg = _apply_overlay(cfg, cli_overrides)
    return cfg


def _apply_overlay(cfg: Config, data: Dict[str, Any]) -> Config:
    valid = {f.name for f in fields(Config)}
    kwargs: Dict[str, Any] = {}
    for key, value in data.items():
        if key in valid:
            if key in ("model_path", "sessions_root"):
                kwargs[key] = Path(str(value))
            else:
                kwargs[key] = _coerce(key, value)
    return Config(**{**{f.name: getattr(cfg, f.name) for f in fields(cfg)}, **kwargs})


def _apply_env(cfg: Config) -> Config:
    kwargs: Dict[str, Any] = {}
    for env_name, field_name in ENV_VARS.items():
        if env_name in os.environ:
            kwargs[field_name] = _coerce(field_name, os.environ[env_name])
    if not kwargs:
        return cfg
    return Config(**{**{f.name: getattr(cfg, f.name) for f in fields(cfg)}, **kwargs})
