"""Versioned, screening-only Heart result assembled from independent branches."""
from __future__ import annotations

from typing import Mapping

import numpy as np

from .heart_dsp import HeartDSPConfig, analyze_cardiac_dsp, inspect_heart_signal
from .murmur_inference import MurmurParticipantService, MurmurRecording

HEART_SCHEMA_VERSION = "heart-analysis-v1"


def murmur_branch(probability: float, threshold: float, model_version: str,
                  *, preprocessing_version: str = "unknown",
                  threshold_version: str = "unknown") -> dict[str, object]:
    """Adapt a frozen Murmur screening score without coupling to a model file."""
    try:
        probability, threshold = float(probability), float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("Murmur probability and threshold must be numeric") from exc
    if (not np.isfinite(probability) or not np.isfinite(threshold)
            or not (0 <= probability <= 1) or not (0 <= threshold <= 1)):
        raise ValueError("Murmur probability and threshold must be finite values in [0,1]")
    if not model_version or not isinstance(model_version, str):
        raise ValueError("Murmur model_version is required")
    return {"status": "available", "model_version": model_version,
            "preprocessing_version": preprocessing_version,
            "threshold_version": threshold_version,
            "probability": float(probability), "threshold": float(threshold),
            "label": "present" if probability >= threshold else "absent"}


def _adapt_murmur(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is None:
        return {"status": "unavailable", "model_version": None,
                "preprocessing_version": None, "threshold_version": None,
                "probability": None, "threshold": None, "label": None}
    if value.get("status", "available") == "unavailable":
        return _adapt_murmur(None)
    try:
        branch = murmur_branch(float(value["probability"]), float(value["threshold"]),
                               value["model_version"],
                               preprocessing_version=str(value.get("preprocessing_version", "unknown")),
                               threshold_version=str(value.get("threshold_version", "unknown")))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid Murmur branch input") from exc
    if "label" in value and str(value["label"]).lower() != branch["label"]:
        raise ValueError("Murmur label conflicts with probability and threshold")
    return branch


def analyze_heart(audio: np.ndarray, sample_rate: int,
                  *, murmur: Mapping[str, object] | None = None,
                  murmur_service: MurmurParticipantService | None = None,
                  config: HeartDSPConfig = HeartDSPConfig()) -> dict[str, object]:
    """Run CPU-only Heart DSP and package an optional independent Murmur output.

    Invalid audio suppresses every branch, including a supplied Murmur score.
    The function never runs a CNN or supplies a missing Murmur probability.
    """
    if murmur is not None and murmur_service is not None:
        raise ValueError("Supply either an existing Murmur result or a service")
    quality = inspect_heart_signal(audio, sample_rate, config)
    result: dict[str, object] = {"schema_version": HEART_SCHEMA_VERSION,
                                 "mode": "heart", "quality": quality,
                                 "rhythm": None, "cardiac_events": None,
                                 "murmur": None,
                                 "visualization": {"waveform_available": False,
                                                   "spectrogram_available": False,
                                                   "event_annotations_available": False}}
    if not quality["valid"]:
        return result
    rhythm, events = analyze_cardiac_dsp(audio, sample_rate, config)
    result["rhythm"] = rhythm
    result["cardiac_events"] = events
    if murmur_service is not None:
        try:
            supplied = murmur_service.predict_participant(
                [MurmurRecording(np.asarray(audio), sample_rate)])
            result["murmur"] = _adapt_murmur(supplied)
        except Exception:
            # A model/adapter failure must not suppress valid independent DSP.
            result["murmur"] = _adapt_murmur(None)
    else:
        result["murmur"] = _adapt_murmur(murmur)
    result["visualization"] = {"waveform_available": True,
                               "spectrogram_available": False,
                               "event_annotations_available": bool(events["candidate_times_s"])}
    return result
