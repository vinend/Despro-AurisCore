"""Deterministic, training-only audio and spectrogram augmentation."""
from __future__ import annotations

from typing import Any

import numpy as np


def augment_waveform(
    audio: np.ndarray, config: dict[str, Any], rng: np.random.Generator
) -> np.ndarray:
    """Apply bounded gain, shift, and noise without changing signal length."""
    signal = np.asarray(audio, dtype=np.float32).copy()
    if not config.get("augmentation_enabled", False):
        return signal

    gain_db = float(config.get("augmentation_gain_db", 0.0))
    if gain_db > 0:
        signal *= np.float32(10 ** (rng.uniform(-gain_db, gain_db) / 20.0))

    max_shift = int(round(len(signal) * float(config.get("augmentation_time_shift_fraction", 0.0))))
    if max_shift > 0:
        signal = np.roll(signal, int(rng.integers(-max_shift, max_shift + 1)))

    probability = float(config.get("augmentation_noise_probability", 0.0))
    if probability > 0 and rng.random() < probability:
        low = float(config.get("augmentation_snr_db_min", 20.0))
        high = float(config.get("augmentation_snr_db_max", 35.0))
        snr_db = rng.uniform(min(low, high), max(low, high))
        signal_rms = float(np.sqrt(np.mean(signal ** 2)))
        if signal_rms > 0:
            noise_rms = signal_rms / (10 ** (snr_db / 20.0))
            signal += rng.normal(0.0, noise_rms, size=signal.shape).astype(np.float32)
    return signal


def _mask_axis(
    tensor: np.ndarray, axis: int, maximum: int, count: int, rng: np.random.Generator
) -> None:
    length = tensor.shape[axis]
    for _ in range(max(0, count)):
        width = int(rng.integers(0, min(maximum, length) + 1))
        if width == 0:
            continue
        start = int(rng.integers(0, length - width + 1))
        selection = [slice(None)] * tensor.ndim
        selection[axis] = slice(start, start + width)
        tensor[tuple(selection)] = 0.0


def augment_spectrogram(
    tensor: np.ndarray, config: dict[str, Any], rng: np.random.Generator
) -> np.ndarray:
    """Apply SpecAugment-style frequency and time masks to one tensor."""
    result = np.asarray(tensor, dtype=np.float32).copy()
    if not config.get("augmentation_enabled", False):
        return result
    _mask_axis(
        result,
        0,
        int(config.get("augmentation_frequency_mask_bins", 0)),
        int(config.get("augmentation_frequency_mask_count", 1)),
        rng,
    )
    _mask_axis(
        result,
        1,
        int(config.get("augmentation_time_mask_frames", 0)),
        int(config.get("augmentation_time_mask_count", 1)),
        rng,
    )
    return result


def mixup(
    first: np.ndarray,
    first_label: float,
    second: np.ndarray,
    second_label: float,
    alpha: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.float32, float]:
    """Mix two spectrograms and labels, returning the first contribution."""
    if alpha <= 0:
        return first, np.float32(first_label), 1.0
    weight = float(rng.beta(alpha, alpha))
    mixed = weight * first + (1.0 - weight) * second
    label = weight * first_label + (1.0 - weight) * second_label
    return mixed.astype(np.float32), np.float32(label), weight


def cutmix(
    first: np.ndarray,
    first_label: float,
    second: np.ndarray,
    second_label: float,
    alpha: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.float32, float]:
    """Replace one spectrogram rectangle and mix labels by retained area."""
    if alpha <= 0:
        return first, np.float32(first_label), 1.0
    requested = float(rng.beta(alpha, alpha))
    cut_ratio = np.sqrt(1.0 - requested)
    height, width = first.shape[:2]
    cut_h = max(1, int(height * cut_ratio))
    cut_w = max(1, int(width * cut_ratio))
    center_h = int(rng.integers(0, height))
    center_w = int(rng.integers(0, width))
    h0, h1 = max(0, center_h - cut_h // 2), min(height, center_h + cut_h // 2)
    w0, w1 = max(0, center_w - cut_w // 2), min(width, center_w + cut_w // 2)
    result = np.asarray(first, dtype=np.float32).copy()
    result[h0:h1, w0:w1] = second[h0:h1, w0:w1]
    retained = 1.0 - ((h1 - h0) * (w1 - w0) / float(height * width))
    label = retained * first_label + (1.0 - retained) * second_label
    return result, np.float32(label), retained

