"""H021 research-artifact audit and fail-closed Heart Murmur service.

H021 saved five outer-fold evaluation pipelines, but no final inference model
or predeclared ensemble. This module never scores audio with a fold model.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np


EXPERIMENT = "EXP-H021-fold-local-hard-negative-acoustic-mining"
PROTOCOL_SHA256 = "fc288f92085ab8c0487a98bf6b36298e4c061fe9edc6049f33229fe0a5ee533c"
OOF_THRESHOLD = 0.19225345646277395  # Audit metadata; never an inference default.


class FreezeIntegrityError(ValueError):
    """The frozen research metadata is missing or internally inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FreezeIntegrityError(f"Missing or invalid H021 freeze file: {path.name}") from exc
    if not isinstance(value, dict):
        raise FreezeIntegrityError(f"H021 freeze file must be an object: {path.name}")
    return value


def load_h021_freeze(folder: Path) -> dict[str, Any]:
    """Verify lightweight freeze metadata without loading any model or dataset."""
    folder = Path(folder)
    try:
        expected_manifest_hash = (folder / "artifact_manifest_sha256.txt").read_text(
            encoding="utf-8").strip()
        if _sha256(folder / "artifact_manifest.json") != expected_manifest_hash:
            raise FreezeIntegrityError("H021 artifact manifest hash mismatch")
    except OSError as exc:
        raise FreezeIntegrityError("Missing H021 artifact manifest/hash") from exc
    manifest = _read_json(folder / "artifact_manifest.json")
    if (manifest.get("schema_version") != "h021-development-freeze-v1"
            or manifest.get("experiment") != EXPERIMENT
            or manifest.get("deployment", {}).get("status") != "unavailable"
            or manifest.get("deployment", {}).get("final_model_exists") is not False
            or manifest.get("deployment", {}).get("predeclared_ensemble") is not False):
        raise FreezeIntegrityError("H021 freeze cannot authorize deployment inference")
    frozen = manifest.get("frozen_files", {})
    for name in ("protocol.json", "config.json", "metrics.json"):
        entry = frozen.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            raise FreezeIntegrityError(f"Missing freeze hash: {name}")
        try:
            actual = _sha256(folder / name)
        except OSError as exc:
            raise FreezeIntegrityError(f"Missing freeze file: {name}") from exc
        if actual != entry["sha256"]:
            raise FreezeIntegrityError(f"H021 freeze hash mismatch: {name}")
    metrics = _read_json(folder / "metrics.json")
    protocol = _read_json(folder / "protocol.json")
    if (_sha256(folder / "protocol.json") != PROTOCOL_SHA256
            or metrics.get("protocol_sha256") != PROTOCOL_SHA256
            or protocol.get("experiment") != EXPERIMENT
            or metrics.get("experiment") != EXPERIMENT
            or metrics.get("threshold") != OOF_THRESHOLD
            or metrics.get("population") != "568 TRAIN outer-fold OOF participants"
            or metrics.get("confusion_matrix") != [[341, 117], [11, 99]]
            or metrics.get("external_validation_opened") is not False
            or metrics.get("sealed_test_opened") is not False
            or len(manifest.get("folds", [])) != 5):
        raise FreezeIntegrityError("H021 frozen protocol, metrics, or fold inventory conflict")
    return manifest


@dataclass(frozen=True)
class MurmurRecording:
    """One recording in a participant bag; site is optional at this boundary."""

    waveform: np.ndarray
    sample_rate: int
    site: str | None = None


class MurmurParticipantService(Protocol):
    """Version-independent participant scoring boundary for Heart aggregation."""

    def predict_participant(self, recordings: Sequence[MurmurRecording]) -> dict[str, object]: ...


class H021MurmurAdapter:
    """Participant-level interface, deliberately unavailable until deployment is defined."""

    def __init__(self, freeze_folder: Path):
        self.manifest = load_h021_freeze(freeze_folder)
        self.experiment_id = EXPERIMENT

    def predict_participant(self, recordings: Sequence[MurmurRecording]) -> dict[str, object]:
        """Never infer from one arbitrary CV fold or apply its OOF threshold."""
        if not recordings:
            raise ValueError("At least one recording is required for a participant")
        if not all(isinstance(item, MurmurRecording) for item in recordings):
            raise TypeError("Participant bag must contain MurmurRecording values")
        return {"status": "unavailable"}


def audit_fold_linear_parameters(path: Path) -> dict[str, object]:
    """Inspect saved scaler/logistic shapes; this is not a prediction API."""
    try:
        with np.load(path, allow_pickle=False) as data:
            required = {"scaler_mean", "scaler_scale", "scaler_var", "coef", "intercept", "classes", "C"}
            if not required.issubset(data.files):
                raise FreezeIntegrityError("Incomplete fold scaler/logistic archive")
            mean, scale, variance = (np.asarray(data[key]) for key in
                                     ("scaler_mean", "scaler_scale", "scaler_var"))
            coef, intercept = np.asarray(data["coef"]), np.asarray(data["intercept"])
            classes, c = np.asarray(data["classes"]), float(data["C"])
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, FreezeIntegrityError):
            raise
        raise FreezeIntegrityError("Unreadable fold scaler/logistic archive") from exc
    if (mean.shape != (64,) or scale.shape != (64,) or variance.shape != (64,)
            or coef.shape != (1, 64) or intercept.shape != (1,)
            or not np.array_equal(classes, [0, 1]) or not np.isfinite(c) or c <= 0
            or not all(np.isfinite(v).all() for v in (mean, scale, variance, coef, intercept))
            or np.any(scale <= 0) or np.any(variance < 0)):
        raise FreezeIntegrityError("Incompatible 64-dimensional fold scaler/logistic archive")
    return {"feature_dim": 64, "classes": [0, 1], "C": c}


def audit_fold_preprocessing(path: Path) -> dict[str, object]:
    """Read the fold's normalization contract without importing TensorFlow."""
    config = _read_json(path)
    expected = {"sample_rate": 8000, "window_seconds": 5.0, "overlap": 0.5,
                "n_mels": 40, "n_fft": 512, "hop_length": 128,
                "feature_fmax": 2000, "spectrogram_normalization": "per_frequency"}
    if any(config.get(key) != value for key, value in expected.items()):
        raise FreezeIntegrityError("Incompatible H021 fold preprocessing")
    mean = np.asarray(config.get("spectrogram_frequency_mean", []), dtype=float)
    std = np.asarray(config.get("spectrogram_frequency_std", []), dtype=float)
    if (mean.shape != (40,) or std.shape != (40,)
            or not np.isfinite(mean).all() or not np.isfinite(std).all()
            or np.any(std <= 0)):
        raise FreezeIntegrityError("Invalid H021 fold normalization statistics")
    return {"sample_rate": 8000, "window_seconds": 5.0, "n_mels": 40,
            "normalization": "per_frequency", "feature_dim": 64}


def audit_fold_artifacts(manifest: dict[str, Any], source_root: Path,
                         fold_number: int) -> dict[str, object]:
    """Verify one evaluation fold's input files; never authorize inference."""
    if fold_number not in range(1, 6):
        raise FreezeIntegrityError("H021 has exactly five outer folds")
    fold = manifest["folds"][fold_number - 1]
    if fold.get("fold") != fold_number:
        raise FreezeIntegrityError("H021 fold order changed")
    root = Path(source_root).resolve()
    resolved = {}
    for key in ("stage1_model", "normalization", "scaler_logistic"):
        entry = fold.get("artifacts", {}).get(key, {})
        path = (root / str(entry.get("path", ""))).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FreezeIntegrityError(f"Missing or unsafe H021 fold artifact: {key}")
        if _sha256(path) != entry.get("sha256"):
            raise FreezeIntegrityError(f"H021 fold artifact hash mismatch: {key}")
        resolved[key] = path
    preprocessing = audit_fold_preprocessing(resolved["normalization"])
    linear = audit_fold_linear_parameters(resolved["scaler_logistic"])
    if linear["C"] != fold.get("selected_C"):
        raise FreezeIntegrityError("H021 selected C conflicts with saved classifier")
    return {"fold": fold_number, "preprocessing": preprocessing,
            "linear": linear, "stage1_model_sha256": fold["artifacts"]["stage1_model"]["sha256"]}
