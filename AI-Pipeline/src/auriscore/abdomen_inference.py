"""Frozen window-level bowel acoustic activity; no event or disease inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from typing import Any, Callable
import zipfile

import numpy as np

from .analysis_service import AnalysisError, BackendDefinition, BackendOutput
from .heart_inference import load_keras_model, validate_preprocessing
from .model_audit import digest, finite, read_json

DEPLOYMENT_SCHEMA = "abdomen-activity-deployment-v1"
RESULT_SCHEMA = "abdomen-analysis-v1"
BACKEND_VERSION = "abdomen-inference-v1"
TARGET = "bowel_sound_activity"
FILES = {"model.keras", "source_metadata.json", "evaluation.json", "decision.json"}
METRICS = {"accuracy", "recall_sensitivity", "specificity", "precision", "f1", "roc_auc", "pr_auc"}


class AbdomenInferenceError(Exception):
    def __init__(self, code: str):
        self.code = code


def validate_window_evidence(evaluation: dict[str, Any], decision: dict[str, Any]) -> None:
    """Check explicit selection and evidence for the exact window decision rule."""
    keys = ("decision_id", "model_version", "preprocessing_version", "threshold_version", "deployment_run_id")
    if any(not isinstance(decision.get(key), str) or not decision[key].strip() for key in keys):
        raise ValueError("Abdomen deployment identifiers and versions are required")
    if (decision.get("status") != "approved_for_engineering_inference"
            or decision.get("model_role") != "final_deployment_model"
            or decision.get("target") != TARGET):
        raise ValueError("An explicit final bowel-activity model decision is required")
    if (evaluation.get("target") != TARGET or evaluation.get("mode") != "abdomen"
            or evaluation.get("inference_unit") != "window"
            or evaluation.get("aggregation") != "none"
            or evaluation.get("threshold_selection_split") != "validation"
            or evaluation.get("participant_disjoint") is not True
            or evaluation.get("class_mapping") != {"absent": 0, "present": 1}
            or any(evaluation.get(key) != decision[key] for key in keys[1:4])):
        raise ValueError("Evidence must bind this bowel window rule on separate participants")
    if (not isinstance(evaluation.get("dataset_version"), str) or not evaluation["dataset_version"]
            or not isinstance(evaluation.get("split_sha256"), str)
            or len(evaluation["split_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in evaluation["split_sha256"])
            or not isinstance(evaluation.get("participants"), int)
            or isinstance(evaluation["participants"], bool) or evaluation["participants"] < 2):
        raise ValueError("Window evidence needs split provenance and at least two validation participants")
    if not finite(evaluation.get("decision_threshold")) or not 0 <= evaluation["decision_threshold"] <= 1:
        raise ValueError("Invalid window threshold")
    counts = evaluation.get("class_counts", {})
    if not isinstance(counts, dict) or any(not isinstance(counts.get(label), int) or isinstance(counts[label], bool)
                                        or counts[label] < 1 for label in ("absent", "present")):
        raise ValueError("Both validation window classes are required")
    matrix = evaluation.get("confusion_matrix")
    if (not isinstance(matrix, list) or len(matrix) != 2
            or any(not isinstance(row, list) or len(row) != 2 for row in matrix)
            or any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for row in matrix for n in row)):
        raise ValueError("Expected window-level TN/FP/FN/TP matrix")
    (tn, fp), (fn, tp) = matrix
    if tn + fp != counts["absent"] or fn + tp != counts["present"]:
        raise ValueError("Window matrix and class counts disagree")
    sensitivity, specificity = tp / (tp + fn), tn / (tn + fp)
    precision = tp / (tp + fp) if tp + fp else 0.
    f1 = 2 * precision * sensitivity / (precision + sensitivity) if precision + sensitivity else 0.
    expected = {"accuracy": (tn + tp) / (tn + fp + fn + tp), "recall_sensitivity": sensitivity,
                "specificity": specificity, "precision": precision, "f1": f1}
    metrics = evaluation.get("metrics", {})
    if not isinstance(metrics, dict) or any(not finite(metrics.get(k)) or not 0 <= metrics[k] <= 1 for k in METRICS):
        raise ValueError("Finite window-level evaluation metrics are required")
    if any(abs(metrics[k] - value) > 1e-6 for k, value in expected.items()):
        raise ValueError("Declared window metrics disagree with confusion matrix")
    # Abdomen has no PRD metric gate. Require the team's explicit gate, not Heart's.
    gate = decision.get("engineering_gate")
    if (not isinstance(gate, dict) or not {"recall_sensitivity", "specificity"}.issubset(gate)
            or not set(gate).issubset(METRICS)
            or any(not finite(value) or not 0 < value <= 1 for value in gate.values())
            or any(metrics[k] < value for k, value in gate.items())):
        raise ValueError("Evidence must meet the explicitly selected Abdomen engineering gate")


def load_abdomen_deployment(folder: Path) -> dict[str, Any]:
    """Verify immutable weights, normalized target and window-level provenance."""
    folder = Path(folder).resolve()
    manifest = read_json(folder / "manifest.json")
    if (manifest.get("schema_version") != DEPLOYMENT_SCHEMA or manifest.get("mode") != "abdomen"
            or manifest.get("target") != TARGET or manifest.get("deployment_eligible") is not True
            or manifest.get("class_mapping") != {"absent": 0, "present": 1}
            or set(manifest.get("files", {})) != FILES):
        raise ValueError("Expected eligible Abdomen package; audit candidates cannot activate inference")
    for name, entry in manifest["files"].items():
        path = folder / name
        if path.is_symlink() or not path.is_file() or digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Abdomen package integrity failure: {name}")
    metadata, evaluation, decision = (read_json(folder / name) for name in
                                     ("source_metadata.json", "evaluation.json", "decision.json"))
    validate_window_evidence(evaluation, decision)
    validate_preprocessing(metadata)
    config = metadata["config"]
    if (evaluation.get("window_seconds") != config["window_seconds"] or evaluation.get("overlap") != config["overlap"]
            or evaluation.get("tail_policy") != "discard_incomplete"
            or evaluation.get("model_sha256") != manifest["files"]["model.keras"]["sha256"]
            or evaluation.get("preprocessing_sha256") != hashlib.sha256(
                json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()):
        raise ValueError("Evidence must bind weights, frozen preprocessing and window geometry")
    with zipfile.ZipFile(folder / "model.keras") as archive:
        if archive.testzip() is not None or not {"config.json", "metadata.json", "model.weights.h5"}.issubset(archive.namelist()):
            raise ValueError("Incomplete Keras archive")
        layers = json.loads(archive.read("config.json"))["config"]["layers"]
        inputs = [layer["config"] for layer in layers if layer["class_name"] == "InputLayer"]
        if (len(inputs) != 1 or list(inputs[0].get("batch_shape", inputs[0].get("batch_input_shape", [])))[1:] != metadata["input_shape"]
                or layers[-1]["config"].get("units") != 1 or layers[-1]["config"].get("activation") != "sigmoid"):
            raise ValueError("Expected matching binary sigmoid tensor contract")
    return {"folder": folder, "manifest": manifest, "metadata": metadata, "evaluation": evaluation, "decision": decision}


def prepare_abdomen_deployment(model: Path, metadata: Path, evaluation: Path,
                               decision: Path, destination: Path) -> Path:
    """Package supplied final evidence without modifying research artifacts."""
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite Abdomen deployment: {destination}")
    validate_window_evidence(read_json(evaluation), read_json(decision))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".abdomen-package-", dir=destination.parent))
    try:
        for source, name in ((model, "model.keras"), (metadata, "source_metadata.json"),
                             (evaluation, "evaluation.json"), (decision, "decision.json")):
            shutil.copyfile(source, temporary / name)
        manifest = {"schema_version": DEPLOYMENT_SCHEMA, "mode": "abdomen", "target": TARGET,
                    "deployment_eligible": True, "class_mapping": {"absent": 0, "present": 1},
                    "files": {name: {"sha256": digest(temporary / name), "bytes": (temporary / name).stat().st_size} for name in sorted(FILES)}}
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        load_abdomen_deployment(temporary)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            if temporary.resolve().parent != destination.parent.resolve():
                raise ValueError("Unsafe Abdomen temporary package cleanup")
            shutil.rmtree(temporary)
    return destination


class BowelWindowScorer:
    """Raw deterministic scores/times only; never assigns a deployment threshold."""

    def __init__(self, model_path: Path, metadata: dict[str, Any], *, loader: Callable[[Path], Any] = load_keras_model,
                 batch_size: int = 16, expected_model_sha256: str | None = None):
        validate_preprocessing(metadata)
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size <= 0:
            raise ValueError("Batch size must be a positive integer")
        self.metadata = json.loads(json.dumps(metadata, allow_nan=False))
        self.model_path, self.loader, self.batch_size = Path(model_path), loader, batch_size
        self.expected_model_sha256 = expected_model_sha256
        self._model, self._load_failed, self._lock = None, False, RLock()

    def score_windows(self, audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
        from .preprocessing import preprocess
        from .segmentation import segment
        from .spectrogram import extract_spectrogram_tensor

        config = self.metadata["config"]
        audio = np.asarray(audio)
        if (not isinstance(sample_rate, (int, np.integer)) or isinstance(sample_rate, (bool, np.bool_))
                or sample_rate <= 0 or audio.ndim != 1 or not audio.size or not np.isfinite(audio).all()):
            raise AbdomenInferenceError("INVALID_AUDIO")
        if len(audio) / sample_rate < config["window_seconds"]:
            raise AbdomenInferenceError("ABDOMEN_INSUFFICIENT_AUDIO")
        size = round(config["sample_rate"] * config["window_seconds"])
        step = round(size * (1 - config["overlap"]))
        if 1 + max(0, round(len(audio) * config["sample_rate"] / sample_rate) - size) // step > 512:
            raise AbdomenInferenceError("AUDIO_TOO_LARGE")
        try:
            processed = preprocess(audio, sample_rate, config)
        except (ValueError, TypeError):
            raise AbdomenInferenceError("ABDOMEN_PREPROCESSING_FAILED") from None
        with self._lock:
            if self._load_failed:
                raise AbdomenInferenceError("MODEL_LOAD_FAILED")
            if self._model is None:
                try:
                    if self.expected_model_sha256 is not None and digest(self.model_path) != self.expected_model_sha256:
                        raise ValueError("Weights changed after registration")
                    self._model = self.loader(self.model_path)
                    if list(self._model.input_shape)[1:] != self.metadata["input_shape"] or list(self._model.output_shape)[1:] != [1]:
                        raise ValueError("Model tensor contract mismatch")
                except Exception:
                    self._load_failed = True
                    raise AbdomenInferenceError("MODEL_LOAD_FAILED") from None
            windows, tensors, times = [], [], []

            def evaluate() -> None:
                predictions = np.asarray(self._model(np.stack(tensors)[..., None], training=False))
                if predictions.shape != (len(tensors), 1) or not np.isfinite(predictions).all() or not ((predictions >= 0) & (predictions <= 1)).all():
                    raise ValueError("Invalid bowel activity predictions")
                windows.extend({"start_s": start, "end_s": end, "score": float(score)}
                               for (start, end), score in zip(times, predictions[:, 0]))
                tensors.clear()
                times.clear()

            try:
                for start, window, valid in segment(processed, config["sample_rate"], config["window_seconds"], config["overlap"]):
                    tensors.append(extract_spectrogram_tensor(window, config))
                    times.append((start / config["sample_rate"], (start + valid) / config["sample_rate"]))
                    if len(tensors) == self.batch_size:
                        evaluate()
                if tensors:
                    evaluate()
            except Exception:
                raise AbdomenInferenceError("INFERENCE_FAILED") from None
            return {"windows": windows, "analyzed_duration_s": windows[-1]["end_s"],
                    "discarded_tail_s": max(0., len(audio) / sample_rate - windows[-1]["end_s"])}


class AbdomenInferenceBackend:
    """Window decisions and a descriptive summary; no inferred event rate."""

    def __init__(self, deployment: Path, *, loader: Callable[[Path], Any] = load_keras_model,
                 _verified_contract: dict[str, Any] | None = None):
        self.package = _verified_contract if _verified_contract is not None else load_abdomen_deployment(deployment)
        self.scorer = BowelWindowScorer(self.package["folder"] / "model.keras", self.package["metadata"], loader=loader,
                                      expected_model_sha256=self.package["manifest"]["files"]["model.keras"]["sha256"])

    def analyze(self, audio: np.ndarray, sample_rate: int) -> BackendOutput:
        try:
            scoring = self.scorer.score_windows(audio, sample_rate)
        except AbdomenInferenceError as exc:
            invalid = exc.code in {"INVALID_AUDIO", "ABDOMEN_INSUFFICIENT_AUDIO", "ABDOMEN_PREPROCESSING_FAILED"}
            return BackendOutput({"schema_version": RESULT_SCHEMA, "mode": "abdomen",
                                  "quality": {"valid": not invalid, "reason": exc.code if invalid else None}, "activity": None,
                                  "bowel_events": None, "bowel_rate_per_minute": None,
                                  "bowel_rate_variability": None, "pattern_categories": None}, "partial",
                                 [AnalysisError(exc.code, "Bowel activity could not be analyzed for this recording.", "bowel_activity")])
        decision, config = self.package["decision"], self.package["metadata"]["config"]
        threshold = self.package["evaluation"]["decision_threshold"]
        windows = [{**window, "label": "present" if window["score"] >= threshold else "absent"} for window in scoring["windows"]]
        count = sum(window["label"] == "present" for window in windows)
        activity = {"target": TARGET, "inference_unit": "window", "aggregation": "none",
                    "model_version": decision["model_version"], "preprocessing_version": decision["preprocessing_version"],
                    "threshold_version": decision["threshold_version"], "threshold": threshold,
                    "score_kind": "uncalibrated_sigmoid", "probability_is_calibrated": False,
                    "window_seconds": config["window_seconds"], "overlap": config["overlap"], "windows": windows,
                    "window_count": len(windows), "active_window_count": count,
                    "active_window_fraction": count / len(windows), "analyzed_duration_s": scoring["analyzed_duration_s"],
                    "discarded_tail_s": scoring["discarded_tail_s"]}
        return BackendOutput({"schema_version": RESULT_SCHEMA, "mode": "abdomen",
                              "quality": {"valid": True, "reason": None}, "activity": activity,
                              "bowel_events": None, "bowel_rate_per_minute": None,
                              "bowel_rate_variability": None, "pattern_categories": None,
                              "limitations": ["Window activity is not event count, event localization or disease diagnosis.",
                                              "Bowel rate, variability and pattern categories require separate validated analysis."]})

def abdomen_backend_definition(package: Path) -> BackendDefinition:
    contract = load_abdomen_deployment(package)
    return BackendDefinition("abdomen", BACKEND_VERSION, lambda: AbdomenInferenceBackend(package, _verified_contract=contract),
                             model_version=contract["decision"]["model_version"], requires_model=True, deployment_eligible=True)
