"""Copy only H021 metadata into a development freeze; source stays read-only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

EXPERIMENT = "EXP-H021-fold-local-hard-negative-acoustic-mining"
PROTOCOL_HASH = "fc288f92085ab8c0487a98bf6b36298e4c061fe9edc6049f33229fe0a5ee533c"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path, source_root: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": path.relative_to(source_root).as_posix(),
            "bytes": path.stat().st_size, "sha256": sha256(path)}


def freeze(source_root: Path, destination: Path) -> Path:
    """Audit exact completed H021 inputs before writing a new metadata package."""
    source_root, destination = source_root.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Freeze already exists: {destination}")
    analysis = source_root / "analysis" / EXPERIMENT
    results = source_root / "results" / EXPERIMENT
    protocol_path = analysis / "protocol.json"
    if sha256(protocol_path) != PROTOCOL_HASH:
        raise ValueError("H021 protocol hash differs from locked value")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    metrics = json.loads((analysis / "metrics.json").read_text(encoding="utf-8"))
    status = json.loads((results / "status.json").read_text(encoding="utf-8"))
    if (status.get("status") != "completed" or protocol.get("experiment") != EXPERIMENT
            or metrics.get("experiment") != EXPERIMENT
            or metrics.get("protocol_sha256") != PROTOCOL_HASH
            or metrics.get("population") != "568 TRAIN outer-fold OOF participants"
            or metrics.get("threshold") != 0.19225345646277395
            or metrics.get("confusion_matrix") != [[341, 117], [11, 99]]
            or metrics.get("external_validation_opened") is not False
            or metrics.get("sealed_test_opened") is not False
            or status.get("external_validation_opened") is not False
            or status.get("sealed_test_opened") is not False):
        raise ValueError("H021 completion or development boundary does not match the audit")
    frozen_paths = [analysis / name for name in ("protocol.json", "config.json", "metrics.json")]
    records = {path.name: file_record(path, source_root) for path in frozen_paths}
    records["predictions_oof.csv"] = file_record(analysis / "predictions_oof.csv", source_root)
    records["fold_metrics.csv"] = file_record(analysis / "fold_metrics.csv", source_root)
    records["status.json"] = file_record(results / "status.json", source_root)
    folds = []
    for number in range(1, 6):
        folder = results / "folds" / f"fold-{number}"
        completed = json.loads((folder / "completed.json").read_text(encoding="utf-8"))
        if completed.get("fold") != number:
            raise ValueError(f"Wrong fold metadata in fold {number}")
        artifacts = {}
        for key, path in {
            "stage1_model": folder / "stage1" / "best_model.keras",
            "normalization": folder / "stage1" / "normalization_config.json",
            "scaler_logistic": folder / "scaler_logistic.npz",
            "completion": folder / "completed.json",
            "outer_predictions": folder / "outer_predictions.csv",
            "hard_negative_inventory": analysis / "hard_negative_inventory" / f"fold_{number}.csv",
        }.items():
            artifacts[key] = file_record(path, source_root)
        for key, metadata_key in (("stage1_model", "encoder_model_sha256"),
                                  ("normalization", "normalization_sha256"),
                                  ("outer_predictions", "outer_predictions_sha256"),
                                  ("hard_negative_inventory", "hard_negative_inventory_sha256")):
            if artifacts[key]["sha256"] != completed[metadata_key]:
                raise ValueError(f"Fold {number} {key} hash conflicts with completion metadata")
        folds.append({"fold": number, "selected_C": completed["C"],
                      "hard_negative_count": completed["hard_negative_count"],
                      "encoder_weights_sha256": completed["encoder_sha256"],
                      "artifacts": artifacts})
    manifest = {
        "schema_version": "h021-development-freeze-v1", "experiment": EXPERIMENT,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_checkout": "WSL-native ~/projects/Despro-AurisCore/AI-Pipeline (read-only audit)",
        "frozen_files": records, "folds": folds,
        "deployment": {"status": "unavailable", "final_model_exists": False,
                       "predeclared_ensemble": False,
                       "reason": "Only outer-fold evaluation pipelines were produced"},
        "threshold": {"value": metrics["threshold"],
                      "scope": "568 TRAIN outer-fold OOF participant predictions",
                      "usable_for_deployment": False},
    }
    destination.mkdir(parents=True)
    for path in frozen_paths:
        shutil.copyfile(path, destination / path.name)
    manifest_path = destination / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "artifact_manifest_sha256.txt").write_text(
        sha256(manifest_path) + "\n", encoding="utf-8")
    (destination / "README.md").write_text(
        "# H021 development freeze\n\n"
        "This package records the completed TRAIN-only, five-fold OOF H021 result. "
        "The original model files remain in the WSL-native checkout; this package contains hashes and lightweight metadata only. "
        "H021 is the current best development candidate, not a deployment-ready or clinically validated model. "
        "External validation and sealed test were not opened.\n\n"
        "See `artifact_manifest.json`, `decision.md`, and `inference_notes.md`.\n"
        "The manifest itself is locked by `artifact_manifest_sha256.txt`.\n\n"
        "For a read-only compatibility check from WSL, run\n"
        "`python scripts/audit_h021_fold_artifacts.py --source-root ~/projects/Despro-AurisCore/AI-Pipeline`\n"
        "from the Windows checkout's `AI-Pipeline` directory using a Python environment\n"
        "with NumPy. This only verifies fold files; it does not produce Murmur scores.\n",
        encoding="utf-8")
    (destination / "decision.md").write_text(
        "# Development decision\n\n"
        "H021 reduced H020 false positives from 179 to 117 (−62) with FN fixed at 11 and sensitivity 0.90. "
        "Specificity rose 0.6092→0.7445, precision 0.3561→0.4583, F1 0.5103→0.6074, "
        "ROC-AUC 0.8924→0.9028, and PR-AUC 0.8138→0.8302. "
        "It meets the protocol's minimum, strong, and very-strong development criteria; "
        "it does not meet breakthrough. "
        "The predefined final engineering gate still fails: specificity <0.85, precision <0.65, "
        "F1 <0.75, ROC-AUC <0.92, and PR-AUC <0.85. "
        "Freeze research; do not start H022 or open external validation/holdout.\n",
        encoding="utf-8")
    (destination / "inference_notes.md").write_text(
        "# Inference semantics\n\n"
        "H021 saved five fold-specific Stage-1 CNN checkpoints, fold-specific per-frequency normalization, "
        "and fold-specific StandardScaler/L2 LogisticRegression parameters. Each fold uses 64-dimensional "
        "segment embeddings, mean segments per recording, then mean recordings per participant. "
        "Stage-1 input is 8 kHz mono, 5-second windows with 50% overlap, 40-bin log-mel, "
        "n_fft=512, hop=128, feature_fmax=2000 Hz and fold-fit per-frequency normalization. "
        "Training-only augmentation is disabled at evaluation.\n\n"
        "No final all-TRAIN model or predeclared fold ensemble was produced. The five fold pipelines "
        "are evaluation artifacts. Choosing one or averaging them would define a new inference procedure "
        "that does not inherit the reported OOF metrics. The threshold 0.19225345646277395 belongs "
        "only to pooled OOF participant probabilities; do not apply it to a single fold, CNN sigmoid, "
        "new ensemble, or one arbitrary WAV. One-WAV H021 inference is unavailable. "
        "The Heart DSP/file demo continues with `murmur.status=unavailable`. "
        "A future deployment-model decision must be separately specified and evaluated.\n",
        encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True,
                        help="Read-only AI-Pipeline root of completed WSL-native H021")
    parser.add_argument("--destination", type=Path,
                        default=Path(__file__).resolve().parents[1] / "analysis" / "HEART-DEVELOPMENT-FREEZE-H021")
    args = parser.parse_args()
    print(freeze(args.source_root, args.destination))
