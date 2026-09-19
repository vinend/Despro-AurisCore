"""Configurable engineering preprocessing, without learned global statistics."""
from math import gcd
from typing import Any
import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Average channels rather than treating channels as separate examples."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim not in (1, 2) or not x.size or not np.isfinite(x).all():
        raise ValueError("Expected nonempty finite audio, samples by channels")
    return x.mean(axis=1) if x.ndim == 2 else x.copy()


def preprocess(audio: np.ndarray, sr: int, config: dict[str, Any]) -> np.ndarray:
    """Mono, polyphase resampling, DC removal, optional filter, peak normalization."""
    x = to_mono(audio)
    target = int(config["sample_rate"])
    if sr <= 0:
        raise ValueError("Invalid source sampling rate")
    divisor = gcd(sr, target)
    if sr != target:
        x = resample_poly(x, target // divisor, sr // divisor)
    x -= x.mean()
    if config["filter_enabled"]:
        sos = butter(config["filter_order"], [config["filter_low_hz"], config["filter_high_hz"]],
                     btype="bandpass", fs=target, output="sos")
        x = sosfiltfilt(sos, x)
    peak = np.max(np.abs(x))
    if peak < 1e-7:
        raise ValueError("Silent/constant audio after DC removal")
    return (x / peak).astype(np.float32)
