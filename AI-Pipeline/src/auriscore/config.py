"""Configuration loading and early validation."""
from pathlib import Path
from typing import Any
import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Read a YAML configuration and reject invalid DSP/split parameters."""
    with Path(path).open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if config["sample_rate"] <= 0 or config["window_seconds"] <= 0:
        raise ValueError("Sample rate and window length must be positive")
    if not 0 <= config["overlap"] < 1:
        raise ValueError("overlap must be in [0, 1)")
    fractions = [config[f"{s}_fraction"] for s in ("train", "validation", "test")]
    if any(f <= 0 for f in fractions) or abs(sum(fractions) - 1) > 1e-8:
        raise ValueError("Positive train/validation/test fractions must sum to one")
    if not 0 < config["feature_fmax"] <= config["sample_rate"] / 2:
        raise ValueError("feature_fmax must be within Nyquist")
    if not 0 < config["n_mfcc"] <= config["n_mels"]:
        raise ValueError("n_mfcc must be positive and <= n_mels")
    if config["filter_enabled"] and not 0 < config["filter_low_hz"] < config["filter_high_hz"] < config["sample_rate"] / 2:
        raise ValueError("Filter cutoffs must lie within Nyquist")
    return config
