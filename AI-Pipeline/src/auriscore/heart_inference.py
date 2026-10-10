"""Frozen recording-level Murmur inference combined with independent Heart DSP."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from threading import RLock
from typing import Any, Callable

import numpy as np

from .analysis_service import AnalysisError, BackendDefinition, BackendOutput
from .heart_result import analyze_heart, murmur_branch
from .model_audit import digest, finite, read_json

DEPLOYMENT_SCHEMA = "heart-murmur-deployment-v1"
BACKEND_VERSION = "heart-inference-v1"
ENGINEERING_GATE = {"recall_sensitivity": .90, "specificity": .85, "precision": .65,
                    "f1": .75, "roc_auc": .92, "pr_auc": .85}
FILES = {"model.keras", "source_metadata.json", "evaluation.json", "decision.json"}


class MurmurInferenceError(Exception):
    """Stable branch-level failures; runtime internals are not user-facing."""

    def __init__(self, code: str):
        self.code = code


def validate_recording_evidence(evaluation: dict[str, Any], decision: dict[str, Any]) -> None:
    """Require an explicit final-model decision and a matching recording threshold."""
    required = ("decision_id", "model_version", "preprocessing_version", "threshold_version", "deployment_run_id")
    if any(not isinstance(decision.get(key), str) or not decision[key].strip() for key in required):
        raise ValueError("Deployment decision requires identifiers and versions")
    if (decision.get("status") != "approved_for_engineering_inference"
            or decision.get("model_role") != "final_deployment_model"
            or decision.get("target") != "murmur_presence"
            or decision["deployment_run_id"].startswith("EXP-H021")):
        raise ValueError("Research folds/candidates cannot act as final Heart models")
    if (evaluation.get("inference_unit") != "recording"
            or evaluation.get("aggregation") != "mean_window_score"
            or evaluation.get("threshold_selection_split") != "validation"
            or evaluation.get("participant_disjoint") is not True
            or evaluation.get("model_version") != decision["model_version"]
            or evaluation.get("preprocessing_version") != decision["preprocessing_version"]
            or evaluation.get("threshold_version") != decision["threshold_version"]):
        raise ValueError("Evidence must evaluate this model and recording-level rule on separate participants")
    if (not isinstance(evaluation.get("dataset_version"), str) or not evaluation["dataset_version"]
            or not isinstance(evaluation.get("split_sha256"), str)
            or len(evaluation["split_sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in evaluation["split_sha256"])
            or not isinstance(evaluation.get("participants"), int)
            or isinstance(evaluation["participants"], bool) or evaluation["participants"] < 2):
        raise ValueError("Evaluation dataset and split provenance are required")
    threshold = evaluation.get("decision_threshold")
    if not finite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Invalid recording-level threshold")
    counts = evaluation.get("class_counts", {})
    if any(not isinstance(counts.get(label), int) or isinstance(counts[label], bool) or counts[label] < 1 for label in ("absent", "present")):
        raise ValueError("Recording validation must contain both classes")
    metrics = evaluation.get("metrics", {})
    matrix = evaluation.get("confusion_matrix")
    if (not isinstance(matrix, list) or len(matrix) != 2
            or any(not isinstance(row, list) or len(row) != 2 for row in matrix)
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for row in matrix for value in row)):
        raise ValueError("Expected a recording-level TN/FP/FN/TP confusion matrix")
    (tn, fp), (fn, tp) = matrix
    if counts != {"absent": tn + fp, "present": fn + tp}:
        raise ValueError("Evaluation class counts and confusion matrix disagree")
    measured = {"recall_sensitivity": tp / (tp + fn), "specificity": tn / (tn + fp),
                "precision": tp / (tp + fp) if tp + fp else 0,
                "f1": 2 * tp / (2 * tp + fp + fn),
                "accuracy": (tn + tp) / (tn + fp + fn + tp)}
    for name, value in measured.items():
        if not finite(metrics.get(name)) or not np.isclose(metrics[name], value, rtol=0, atol=1e-6):
            raise ValueError(f"Evaluation metric conflicts with confusion matrix: {name}")
    for name, minimum in ENGINEERING_GATE.items():
        value = metrics.get(name)
        if not finite(value) or not minimum <= value <= 1:
            raise ValueError(f"Heart engineering gate not met: {name}")


def validate_preprocessing(metadata: dict[str, Any]) -> None:
    """Validate frozen tensors using the exact existing preprocessing implementation."""
    from .spectrogram import spectrogram_shape, validate_spectrogram_config

    config = metadata["config"]
    if not isinstance(config, dict):
        raise ValueError("Expected frozen preprocessing configuration")
    for key in ("sample_rate", "n_fft", "hop_length", "n_mels"):
        if not isinstance(config.get(key), int) or isinstance(config[key], bool) or config[key] <= 0:
            raise ValueError(f"Invalid integer preprocessing field: {key}")
    for key in ("window_seconds", "cnn_top_db"):
        if not finite(config.get(key)) or config[key] <= 0:
            raise ValueError(f"Invalid preprocessing field: {key}")
    if (not finite(config.get("overlap")) or not 0 <= config["overlap"] < 1
            or round(config["sample_rate"] * config["window_seconds"] * (1 - config["overlap"])) < 1):
        raise ValueError("Invalid frozen segmentation")
    samples = round(config["sample_rate"] * config["window_seconds"])
    if not 1 < config["n_fft"] <= samples <= 2_000_000:
        raise ValueError("Frozen window/FFT exceeds the supported sample limit")
    if not isinstance(config.get("filter_enabled"), bool):
        raise ValueError("Explicit filter configuration is required")
    if config["filter_enabled"] and not 0 < config["filter_low_hz"] < config["filter_high_hz"] < config["sample_rate"] / 2:
        raise ValueError("Invalid frozen filter band")
    validate_spectrogram_config(config)
    expected = [*spectrogram_shape(config), 1]
    if metadata.get("input_shape") != expected:
        raise ValueError("Frozen preprocessing and tensor shape disagree")


def load_heart_deployment(folder: Path) -> dict[str, Any]:
    """Verify package bytes and recording-level evidence before registering inference."""
    folder = Path(folder).resolve()
    manifest = read_json(folder / "manifest.json")
    if (manifest.get("schema_version") != DEPLOYMENT_SCHEMA
            or manifest.get("mode") != "heart" or manifest.get("target") != "murmur_presence"
            or manifest.get("deployment_eligible") is not True
            or set(manifest.get("files", {})) != FILES):
        raise ValueError("Expected an eligible Heart deployment package, not an audit candidate")
    for name, entry in manifest["files"].items():
        path = folder / name
        if path.is_symlink() or not path.is_file() or digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Heart deployment integrity failure: {name}")
    metadata = read_json(folder / "source_metadata.json")
    evaluation = read_json(folder / "evaluation.json")
    decision = read_json(folder / "decision.json")
    validate_recording_evidence(evaluation, decision)
    validate_preprocessing(metadata)
    if evaluation.get("model_sha256") != manifest["files"]["model.keras"]["sha256"]:
        raise ValueError("Evaluation evidence belongs to different model weights")
    config_hash = hashlib.sha256(json.dumps(metadata["config"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    if evaluation.get("preprocessing_sha256") != config_hash:
        raise ValueError("Evaluation evidence belongs to different preprocessing")
    with zipfile.ZipFile(folder / "model.keras") as archive:
        if archive.testzip() is not None or not {"config.json", "metadata.json", "model.weights.h5"}.issubset(archive.namelist()):
            raise ValueError("Corrupt or incomplete Keras deployment archive")
        layers = json.loads(archive.read("config.json"))["config"]["layers"]
        inputs = [layer["config"] for layer in layers if layer["class_name"] == "InputLayer"]
        if (len(inputs) != 1 or list(inputs[0].get("batch_shape", inputs[0].get("batch_input_shape", [])))[1:] != metadata["input_shape"]
                or layers[-1]["config"].get("units") != 1 or layers[-1]["config"].get("activation") != "sigmoid"):
            raise ValueError("Expected matching binary sigmoid CNN tensor contract")
    return {"folder": folder, "manifest": manifest, "metadata": metadata,
            "evaluation": evaluation, "decision": decision}


def prepare_heart_deployment(model: Path, metadata: Path, evaluation: Path,
                             decision: Path, destination: Path) -> Path:
    """Publish a new package only when supplied final-model evidence passes checks."""
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite Heart deployment: {destination}")
    validate_recording_evidence(read_json(evaluation), read_json(decision))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".heart-package-", dir=destination.parent))
    try:
        for source, name in ((model, "model.keras"), (metadata, "source_metadata.json"),
                             (evaluation, "evaluation.json"), (decision, "decision.json")):
            shutil.copyfile(source, temporary / name)
        manifest = {"schema_version": DEPLOYMENT_SCHEMA, "mode": "heart",
                    "target": "murmur_presence", "deployment_eligible": True,
                    "files": {name: {"sha256": digest(temporary / name), "bytes": (temporary / name).stat().st_size} for name in sorted(FILES)}}
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        load_heart_deployment(temporary)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            if temporary.resolve().parent != destination.parent.resolve():
                raise ValueError("Unsafe Heart temporary package cleanup")
            shutil.rmtree(temporary)
    return destination


def load_keras_model(path: Path) -> Any:
    """Load trusted frozen weights in inference-only safe mode."""
    from .cnn import require_tensorflow

    return require_tensorflow().keras.models.load_model(path, compile=False, safe_mode=True)


class RecordingMurmurScorer:
    """Raw recording score only; this utility does not select thresholds or labels."""

    def __init__(self, model_path: Path, metadata: dict[str, Any], *,
                 loader: Callable[[Path], Any] = load_keras_model, batch_size: int = 16,
                 expected_model_sha256: str | None = None):
        validate_preprocessing(metadata)
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size <= 0:
            raise ValueError("Batch size must be a positive integer")
        self.model_path = Path(model_path)
        self.metadata = json.loads(json.dumps(metadata, allow_nan=False))
        self.loader, self.batch_size = loader, batch_size
        self.expected_model_sha256 = expected_model_sha256
        self._model = None
        self._load_failed = False
        self._lock = RLock()

    def score(self, audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
        """Apply frozen preprocessing, deterministic windows and equal-weight averaging."""
        from .preprocessing import preprocess
        from .segmentation import segment
        from .spectrogram import extract_spectrogram_tensor

        config = self.metadata["config"]
        if len(audio) / sample_rate < config["window_seconds"]:
            raise MurmurInferenceError("MURMUR_INSUFFICIENT_AUDIO")
        try:
            processed = preprocess(audio, sample_rate, config)
        except (ValueError, TypeError):
            raise MurmurInferenceError("MURMUR_PREPROCESSING_FAILED") from None
        with self._lock:
            if self._load_failed:
                raise MurmurInferenceError("MODEL_LOAD_FAILED")
            if self._model is None:
                try:
                    if self.expected_model_sha256 is not None and digest(self.model_path) != self.expected_model_sha256:
                        raise ValueError("Model weights changed after registration")
                    self._model = self.loader(self.model_path)
                    if (list(self._model.input_shape)[1:] != self.metadata["input_shape"]
                            or list(self._model.output_shape)[1:] != [1]):
                        raise ValueError("Loaded model tensor contract mismatch")
                except Exception:
                    self._load_failed = True
                    raise MurmurInferenceError("MODEL_LOAD_FAILED") from None
            scores, batch = [], []

            def evaluate() -> None:
                tensor = np.stack(batch)[..., None]
                output = np.asarray(self._model(tensor, training=False))
                if output.shape != (len(batch), 1) or not np.isfinite(output).all() or not ((0 <= output) & (output <= 1)).all():
                    raise ValueError("Invalid Murmur predictions")
                scores.extend(float(value) for value in output[:, 0])
                batch.clear()

            try:
                for _, window, _ in segment(processed, config["sample_rate"], config["window_seconds"], config["overlap"]):
                    batch.append(extract_spectrogram_tensor(window, config))
                    if len(batch) == self.batch_size:
                        evaluate()
                if batch:
                    evaluate()
            except Exception:
                raise MurmurInferenceError("INFERENCE_FAILED") from None
            return {"score": float(np.mean(scores)), "window_count": len(scores)}


class HeartInferenceBackend:
    """Unified real Heart analysis; model failure never discards independent DSP."""

    def __init__(self, deployment: Path, *, loader: Callable[[Path], Any] = load_keras_model,
                 _verified_contract: dict[str, Any] | None = None):
        self.package = _verified_contract if _verified_contract is not None else load_heart_deployment(deployment)
        self.scorer = RecordingMurmurScorer(self.package["folder"] / "model.keras",
                                           self.package["metadata"], loader=loader,
                                           expected_model_sha256=self.package["manifest"]["files"]["model.keras"]["sha256"])

    def analyze(self, audio: np.ndarray, sample_rate: int) -> BackendOutput:
        result = analyze_heart(audio, sample_rate)
        if not result["quality"]["valid"]:
            return BackendOutput(result, "partial", [AnalysisError("LOW_SIGNAL_QUALITY", "Heart signal is insufficient.", "quality")])
        try:
            scoring = self.scorer.score(audio, sample_rate)
        except MurmurInferenceError as exc:
            return BackendOutput(result, "partial", [AnalysisError(exc.code,
                "Murmur analysis could not process this recording; Heart DSP remains available.", "murmur")])
        decision, evaluation = self.package["decision"], self.package["evaluation"]
        result["murmur"] = murmur_branch(scoring["score"], evaluation["decision_threshold"],
            decision["model_version"], preprocessing_version=decision["preprocessing_version"],
            threshold_version=decision["threshold_version"])
        result["murmur"].update(inference_unit="recording", aggregation="mean_window_score",
                                window_count=scoring["window_count"], score_kind="uncalibrated_sigmoid",
                                probability_is_calibrated=False)
        return BackendOutput(result)


def heart_backend_definition(package: Path) -> BackendDefinition:
    """Register only a verified final Heart package with the shared service."""
    contract = load_heart_deployment(package)
    return BackendDefinition("heart", BACKEND_VERSION, lambda: HeartInferenceBackend(package, _verified_contract=contract),
                             model_version=contract["decision"]["model_version"],
                             requires_model=True, deployment_eligible=True)
