"""Nonfatal per-file quality checks and strict metadata validation."""
import hashlib
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
import soundfile as sf

MANIFEST_COLUMNS = [
    "dataset_source", "subject_id", "recording_id", "file_path", "label",
    "murmur_label", "outcome_label", "auscultation_location",
    "original_sampling_rate", "duration_sec", "split", "license", "notes",
    "additional_id", "subject_group", "sha256", "quality_flag",
]


def sha256(path: Path) -> str:
    """Stream a file digest without loading the whole file."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_audio(path: Path) -> dict[str, Any]:
    """Return quality measurements or an error; bad audio never aborts a scan."""
    result: dict[str, Any] = {"valid": False, "error": "", "quality_flag": "invalid"}
    try:
        result["sha256"] = sha256(path)
        x, sr = sf.read(path, dtype="float64", always_2d=True)
        result.update(channels=x.shape[1], sampling_rate=sr, duration_sec=len(x) / sr,
                      empty=x.size == 0, nan_count=int(np.isnan(x).sum()),
                      inf_count=int(np.isinf(x).sum()))
        if not x.size:
            raise ValueError("Empty audio")
        if not np.isfinite(x).all():
            raise ValueError("NaN/Inf samples")
        rms = float(np.sqrt(np.mean(x ** 2)))
        clipping = float(np.mean(np.abs(x) >= 0.999))
        flags = []
        if clipping > 0.01:
            flags.append("clipping")
        if rms < 1e-7:
            flags.append("silent")
        if len(x) / sr < 5:
            flags.append("short")
        result.update(valid=True, rms=rms, clipping_ratio=clipping,
                      quality_flag=";".join(flags) or "ok")
    except (OSError, RuntimeError, ValueError) as exc:
        result["error"] = str(exc)
    return result


def validate_manifest(frame: pd.DataFrame, require_subjects: bool = False) -> None:
    """Reject malformed schemas/IDs; optionally fail on missing subject IDs."""
    missing = set(MANIFEST_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Manifest columns missing: {sorted(missing)}")
    if frame.recording_id.isna().any() or frame.recording_id.eq("").any() or frame.recording_id.duplicated().any():
        raise ValueError("Missing or duplicate recording IDs")
    if not frame.label.isin(["Absent", "Present", "Unknown", ""]).all():
        raise ValueError("Unexpected murmur target label")
    if not frame.label.equals(frame.murmur_label):
        raise ValueError("Target must match murmur_label, never outcome_label")
    if require_subjects and (frame.subject_id.isna() | frame.subject_id.eq("")).any():
        raise ValueError("Missing subject ID: subject-wise splitting cannot be guaranteed")
