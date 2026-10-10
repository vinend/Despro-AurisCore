"""Deterministic lung frame features and interval targets, including tail masks."""
import hashlib
import json
import numpy as np
from .preprocessing import preprocess
from .spectrogram import extract_spectrogram_tensor, validate_spectrogram_config


def validate_config(config):
    validate_spectrogram_config(config)
    if (config["sample_rate"] != 8000 or config.get("spectrogram_center") is not False
            or config.get("spectrogram_type") != "logmel" or config.get("spectrogram_normalization") != "none"
            or config["feature_fmax"] >= 2000 or not 0 <= config["overlap"] < 1
            or config["window_seconds"] <= 0 or config["n_fft"] > config["sample_rate"] * config["window_seconds"]):
        raise ValueError("Invalid lung feature geometry")
    classes = config.get("classes", [])
    from .dataset_lung import CLASSES
    if not classes or len(classes) != len(set(classes)) or not set(classes).issubset(CLASSES):
        raise ValueError("Explicit unique supported classes required")


def config_digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()


def windows(audio, rate, events, config, *, valid_end_s=None, coverage=False):
    """Yield time-major tensors, multi-label targets and per-class validity masks."""
    validate_config(config)
    x = preprocess(audio, rate, config)
    target_rate, fft, hop = config["sample_rate"], config["n_fft"], config["hop_length"]
    size = round(config["window_seconds"] * target_rate)
    step = (round(size * (1 - config["overlap"])) // hop) * hop
    if step < 1:
        raise ValueError("Invalid window hop")
    valid_end_s = min(len(x) / target_rate, valid_end_s if valid_end_s is not None else len(x) / target_rate)
    starts = list(range(0, max(1, len(x) - size + 1), step))
    if starts[-1] + size < len(x):
        starts.append(starts[-1] + step)
    for start in starts:
        block = x[start:start + size]
        block = np.pad(block, (0, size - len(block)))
        feature = extract_spectrogram_tensor(block, config).T.astype(np.float32)
        times = (start + np.arange(len(feature)) * hop + fft / 2) / target_rate
        ends = (start + np.arange(len(feature)) * hop + fft) / target_rate
        mask = np.repeat((ends <= valid_end_s + 1e-9)[:, None], len(config["classes"]), axis=1)
        targets = np.zeros_like(mask, dtype=np.float32)
        for event in events:
            if event["label"] in config["classes"]:
                index = config["classes"].index(event["label"])
                # Any overlap catches short crackles; validity still requires a complete frame.
                hit = (ends > event["start_s"]) & (times - fft / (2 * target_rate) < event["end_s"])
                targets[hit, index] = 1
        if not coverage:
            mask &= targets > 0  # Unverified absence must never become a negative label.
        else:
            # Label absence is supervised only inside annotated breathing regions.
            # Outside those regions only explicitly positive event labels are valid.
            covered = np.zeros(len(feature), dtype=bool)
            for event in events:
                if event["label"] in {"inhalation", "exhalation"}:
                    covered |= (times >= event["start_s"]) & (times < event["end_s"])
            mask &= covered[:, None] | (targets > 0)
        yield {"start_sample": start, "features": feature, "targets": targets,
               "mask": mask.astype(np.float32), "times_s": times}


def fit_normalization(features, masks):
    """Fit only supplied TRAIN valid frames; reject missing support."""
    selected = [x[np.any(m > 0, axis=1)] for x, m in zip(features, masks)]
    values = np.concatenate(selected)
    if not len(values):
        raise ValueError("No valid training frames")
    return values.mean(axis=0).astype(np.float32), np.maximum(values.std(axis=0), 1e-5).astype(np.float32)
