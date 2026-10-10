"""Spectrogram tensors for CNN training, inference, and visual quality control.

The model consumes floating-point arrays, not rendered PNG files.  This keeps
the frequency/time bins exact and avoids colormap, resize, and quantization
artifacts.  Images may still be rendered separately for human inspection.
"""
from __future__ import annotations

from typing import Any

import numpy as np


SUPPORTED_SPECTROGRAMS = {"logmel", "logstft"}
SUPPORTED_NORMALIZATIONS = {"minmax", "none", "per_frequency"}


def spectrogram_shape(config: dict[str, Any]) -> tuple[int, int]:
    """Return the deterministic frequency/time shape for one configured window."""
    validate_spectrogram_config(config)
    kind = str(config.get("spectrogram_type", "logmel"))
    frequency_bins = int(config["n_mels"]) if kind == "logmel" else int(config["n_fft"]) // 2 + 1
    samples = int(round(float(config["sample_rate"]) * float(config["window_seconds"])))
    time_frames = 1 + int(samples // int(config["hop_length"]))
    return (frequency_bins, time_frames)
def validate_spectrogram_config(config: dict[str, Any]) -> None:
    """Reject feature settings that would silently produce invalid tensors."""
    kind = str(config.get("spectrogram_type", "logmel"))
    normalization = str(config.get("spectrogram_normalization", "minmax"))
    if kind not in SUPPORTED_SPECTROGRAMS:
        raise ValueError(f"spectrogram_type must be one of {sorted(SUPPORTED_SPECTROGRAMS)}")
    if normalization not in SUPPORTED_NORMALIZATIONS:
        raise ValueError(
            f"spectrogram_normalization must be one of {sorted(SUPPORTED_NORMALIZATIONS)}"
        )
    sample_rate = int(config["sample_rate"])
    fmin = float(config.get("feature_fmin", 0.0))
    fmax = float(config["feature_fmax"])
    if not 0 <= fmin < fmax <= sample_rate / 2:
        raise ValueError("Spectrogram frequency limits must satisfy 0 <= fmin < fmax <= Nyquist")
    if int(config["n_fft"]) <= 1 or int(config["hop_length"]) <= 0:
        raise ValueError("n_fft must exceed one and hop_length must be positive")
    if kind == "logmel" and int(config["n_mels"]) <= 0:
        raise ValueError("n_mels must be positive for a log-mel spectrogram")


def _power_spectrogram(audio: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    import librosa
    power = np.abs(
        librosa.stft(
            audio,
            n_fft=int(config["n_fft"]),
            hop_length=int(config["hop_length"]),
            center=bool(config.get("spectrogram_center", True)),
        )
    ) ** 2
    kind = str(config.get("spectrogram_type", "logmel"))
    if kind == "logmel":
        return librosa.feature.melspectrogram(
            S=power,
            sr=int(config["sample_rate"]),
            n_fft=int(config["n_fft"]),
            n_mels=int(config["n_mels"]),
            fmin=float(config.get("feature_fmin", 0.0)),
            fmax=float(config["feature_fmax"]),
        )
    frequencies = librosa.fft_frequencies(
        sr=int(config["sample_rate"]), n_fft=int(config["n_fft"])
    )
    mask = (frequencies >= float(config.get("feature_fmin", 0.0))) & (
        frequencies <= float(config["feature_fmax"])
    )
    return power[mask]


def _normalise(db: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    mode = str(config.get("spectrogram_normalization", "minmax"))
    top_db = float(config.get("cnn_top_db", 80.0))
    if mode == "minmax":
        # With ref=max the dB range is [-top_db, 0].  Explicit clipping also
        # makes older model configurations deterministic.
        result = np.clip((db + top_db) / top_db, 0.0, 1.0)
    elif mode == "none":
        result = db
    else:
        means = np.asarray(config.get("spectrogram_frequency_mean", []), dtype=np.float32)
        stds = np.asarray(config.get("spectrogram_frequency_std", []), dtype=np.float32)
        if means.shape != (db.shape[0],) or stds.shape != (db.shape[0],):
            raise ValueError(
                "per_frequency normalization requires training-set mean/std for every frequency bin"
            )
        if np.any(stds <= 0) or not np.isfinite(means).all() or not np.isfinite(stds).all():
            raise ValueError("Invalid spectrogram training normalization statistics")
        result = (db - means[:, np.newaxis]) / stds[:, np.newaxis]
        clip = float(config.get("spectrogram_normalization_clip", 5.0))
        if clip > 0:
            result = np.clip(result, -clip, clip)
    return np.asarray(result, dtype=np.float32)


def extract_spectrogram_tensor(audio: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    """Convert finite mono audio into a single-channel-ready float tensor."""
    signal = np.asarray(audio)
    if signal.ndim != 1 or not signal.size or not np.isfinite(signal).all():
        raise ValueError("Spectrogram extraction requires finite, nonempty mono audio")
    validate_spectrogram_config(config)
    power = _power_spectrogram(signal, config)
    top_db = float(config.get("cnn_top_db", 80.0))
    if top_db <= 0:
        raise ValueError("cnn_top_db must be positive")
    import librosa
    db = librosa.power_to_db(power, ref=np.max, top_db=top_db)
    tensor = _normalise(db, config)
    if tensor.ndim != 2 or not tensor.size or not np.isfinite(tensor).all():
        raise ValueError("Spectrogram extraction produced an invalid tensor")
    return tensor

