"""Reproducible acoustic descriptors; metadata never enters the feature vector."""
from typing import Any
import librosa
import numpy as np


def extract_features(audio: np.ndarray, config: dict[str, Any]) -> dict[str, float]:
    """Aggregate MFCC, deltas, log-mel, RMS, centroid, ZCR and temporal stats."""
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError("Features require finite, nonempty mono audio")
    sr, n_fft, hop = config["sample_rate"], config["n_fft"], config["hop_length"]
    power = np.abs(librosa.stft(audio, n_fft=n_fft, hop_length=hop)) ** 2
    mel = librosa.feature.melspectrogram(S=power, sr=sr, n_fft=n_fft,
                                       n_mels=config["n_mels"], fmax=config["feature_fmax"])
    logmel = librosa.power_to_db(mel, ref=1.0)
    mfcc = librosa.feature.mfcc(S=logmel, n_mfcc=config["n_mfcc"])
    groups = {
        "mfcc": mfcc, "delta": librosa.feature.delta(mfcc, mode="nearest"),
        "logmel": logmel,
        "rms": librosa.feature.rms(y=audio, frame_length=n_fft, hop_length=hop),
        "centroid": librosa.feature.spectral_centroid(S=np.sqrt(power), sr=sr, n_fft=n_fft),
        "zcr": librosa.feature.zero_crossing_rate(audio, frame_length=n_fft, hop_length=hop),
    }
    result = {}
    for name, values in groups.items():
        for stat, operation in [("mean", np.mean), ("std", np.std), ("median", np.median),
                                ("min", np.min), ("max", np.max)]:
            for index, value in enumerate(operation(values, axis=1)):
                result[f"f_{name}_{index}_{stat}"] = float(value)
    result.update(f_amplitude_mean=float(audio.mean()), f_amplitude_std=float(audio.std()),
                  f_abs_mean=float(np.abs(audio).mean()),
                  f_crest_factor=float(np.max(np.abs(audio)) / max(np.sqrt(np.mean(audio ** 2)), 1e-12)))
    if not np.isfinite(list(result.values())).all():
        raise ValueError("Nonfinite feature vector")
    return result
