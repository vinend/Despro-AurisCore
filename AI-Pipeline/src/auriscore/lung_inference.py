"""Verified Lung packages, bounded temporal inference and explicit availability."""
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from .acquisition_lung import digest
from .analysis_service import BackendDefinition, BackendOutput, AnalysisError
from .lung_preprocessing import validate_config, windows
from .lung_evaluation import merge_predictions, extract_events
from .lung_dsp import respiratory_measurements

FILES = {"model.keras", "normalization.npz", "config.json", "evaluation.json", "decision.json"}
REQUIRED = {"inhalation", "exhalation", "wheeze", "rhonchi", "crackle"}


def verify_package(folder):
    """Bind immutable weights/preprocessing to a specific engineering decision."""
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "manifest.json").read_text())
    if (manifest.get("schema_version") != "lung-deployment-v1" or manifest.get("mode") != "lung"
            or not isinstance(manifest.get("model_version"), str) or not manifest["model_version"].strip()
            or manifest.get("deployment_eligible") is not True or set(manifest.get("files", {})) != FILES):
        raise ValueError("An eligible Lung deployment package is required")
    for name, entry in manifest["files"].items():
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Lung package integrity failure")
    config = json.loads((folder / "config.json").read_text())
    validate_config(config)
    if config.get("annotation_coverage_verified") is not True:
        raise ValueError("Verified annotation coverage required")
    evidence, decision = (json.loads((folder / name).read_text()) for name in ("evaluation.json", "decision.json"))
    model_hash = manifest["files"]["model.keras"]["sha256"]
    if (decision.get("status") != "approved_for_engineering_inference"
            or decision.get("model_role") != "final_deployment_model"
            or decision.get("model_sha256") != model_hash or evidence.get("model_sha256") != model_hash
            or evidence.get("config_sha256") != manifest["files"]["config.json"]["sha256"]
            or evidence.get("normalization_sha256") != manifest["files"]["normalization.npz"]["sha256"]
            or evidence.get("classes") != config["classes"] or evidence.get("group_disjoint") is not True
            or evidence.get("grouping") != "shifted_recording_date" or evidence.get("patient_disjoint_verified") is not False
            or evidence.get("threshold_selection_role") not in {"development_validation", "train_only_oof"}
            or evidence.get("evaluation_role") != "locked_official_test"
            or not isinstance(evidence.get("split_sha256"), str) or len(evidence["split_sha256"]) != 64
            or not isinstance(decision.get("decision_id"), str) or not decision["decision_id"].strip() or decision.get("model_version") != manifest.get("model_version")
            or evidence.get("model_version") != manifest.get("model_version")):
        raise ValueError("Final model decision and exact-rule evidence required")
    thresholds = evidence.get("thresholds", [])
    if len(thresholds) != len(config["classes"]) or not np.isfinite(thresholds).all() or np.any(np.asarray(thresholds) < 0) or np.any(np.asarray(thresholds) > 1):
        raise ValueError("Invalid class thresholds")
    gate = decision.get("engineering_gate", {})
    metrics = evidence.get("metrics", [])
    if not gate or set(gate) != set(config["classes"]) or len(metrics) != len(gate):
        raise ValueError("Explicit per-class Lung eligibility gate required")
    for label, metric in zip(config["classes"], metrics):
        counts = [metric.get(k) for k in ("tn", "fp", "fn", "tp")]
        if any(type(v) is not int or v < 0 for v in counts):
            raise ValueError("Evidence requires frame confusion counts")
        tn, fp, fn, tp = counts
        if not tp + fn or not tn + fp:
            raise ValueError("Both classes required in evaluation")
        computed = {"sensitivity": tp / (tp + fn), "specificity": tn / (tn + fp),
                    "f1": 2 * tp / (2 * tp + fp + fn)}
        if any(not isinstance(metric.get(k), (int, float)) or not np.isfinite(metric[k]) or abs(metric[k] - v) > 1e-6 for k, v in computed.items()):
            raise ValueError("Metrics disagree with counts")
        if not gate[label] or not set(gate[label]).issubset(computed):
            raise ValueError("Unsupported/empty gate")
        if any(not isinstance(v, (int, float)) or not np.isfinite(v) or not 0 < v <= 1 or computed[k] < v for k, v in gate[label].items()):
            raise ValueError("Lung gate not met")
    post = evidence.get("postprocessing", {})
    if set(post) != {"minimum_s", "merge_gap_s"} or any(not isinstance(v, (int, float)) or not np.isfinite(v) or not 0 <= v <= 2 for v in post.values()):
        raise ValueError("Exact event postprocessing required")
    with np.load(folder / "normalization.npz", allow_pickle=False) as data:
        mean, std = data["mean"], data["std"]
    if mean.shape != (config["n_mels"],) or std.shape != mean.shape or not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std <= 0):
        raise ValueError("Invalid Lung normalization")
    return manifest, config, evidence, mean, std


def prepare_package(source, destination, *, model_version):
    """Package only explicitly selected final weights; never promotes research automatically."""
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError("Never overwrite an existing package")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        staging = Path(directory) / "package"
        staging.mkdir()
        for name in FILES:
            shutil.copyfile(source / name, staging / name)
        manifest = {"schema_version": "lung-deployment-v1", "mode": "lung", "model_version": model_version,
                    "deployment_eligible": True, "files": {name: {"bytes": (staging / name).stat().st_size,
                    "sha256": digest(staging / name)} for name in sorted(FILES)}}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
        verify_package(staging)
        staging.replace(destination)
    return manifest


class LungInferenceBackend:
    def __init__(self, folder, *, loader=None):
        self.folder = Path(folder)
        self.manifest, self.config, self.evidence, self.mean, self.std = verify_package(folder)
        if loader is None:
            from .heart_inference import load_keras_model
            loader = load_keras_model
        self.model = loader(self.folder / "model.keras")

    def analyze(self, audio, sample_rate):
        blocks = []
        for block in windows(audio, sample_rate, [], self.config):
            x = np.clip((block["features"] - self.mean) / self.std, -5, 5)
            output = np.asarray(self.model(x[None], training=False))[0]
            expected = (len(x), len(self.config["classes"]))
            if output.shape != expected or not np.isfinite(output).all() or np.any((output < 0) | (output > 1)):
                raise ValueError("Invalid Lung model output")
            valid = min(round(len(audio) / sample_rate * 8000) - block["start_sample"], round(self.config["window_seconds"] * 8000))
            blocks.append((block["start_sample"], output, valid))
        times, scores = merge_predictions(blocks, sample_rate=8000, hop_length=self.config["hop_length"], n_fft=self.config["n_fft"])
        if not len(times):
            raise ValueError("No complete frames")
        duration = len(audio) / sample_rate
        events = extract_events(times, scores, self.config["classes"], self.evidence["thresholds"],
                                hop_s=self.config["hop_length"] / 8000, duration_s=duration, **self.evidence["postprocessing"])
        phases = [e for e in events if e["label"] in {"inhalation", "exhalation"}]
        measured = respiratory_measurements(phases, duration)
        missing = sorted(REQUIRED - set(self.config["classes"]))
        errors = [AnalysisError("LUNG_BRANCH_UNAVAILABLE", f"No trained {label} output.", label) for label in missing]
        if measured["reason"]:
            errors.append(AnalysisError("LUNG_INSUFFICIENT_CYCLES", "Respiratory measurements are unavailable for this recording.", "respiratory_metrics"))
        result = {"schema_version": "lung-analysis-v1", "mode": "lung", "quality": {"valid": True, "reason": None},
                  "model_version": self.manifest["model_version"], "supported_classes": self.config["classes"],
                  "sound_events": [e for e in events if e not in phases], "phase_intervals": phases,
                  "class_scores": [{"label": label, "maximum_frame_score": float(scores[:, i].max()),
                                    "threshold": self.evidence["thresholds"][i]} for i, label in enumerate(self.config["classes"])],
                  "respiratory": measured, "analyzed_duration_s": duration,
                  "limitations": ["Prototype acoustic screening; not a diagnosis.", "HF labels are imperfect; date groups do not verify patient independence.",
                                   "Frame sigmoid scores are not calibrated probabilities."]}
        return BackendOutput(result, "partial" if errors else "completed", errors)


def lung_backend_definition(folder):
    manifest, *_ = verify_package(folder)
    return BackendDefinition("lung", "lung-inference-v1", lambda: LungInferenceBackend(folder),
                             model_version=manifest["model_version"], requires_model=True, deployment_eligible=True)
