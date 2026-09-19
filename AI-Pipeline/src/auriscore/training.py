"""SVM baseline with validation-only threshold selection and sealed holdout."""
import hashlib
import json
import platform
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from .evaluation import evaluate, plot_confusion, select_screening_threshold
from .splitting import assert_no_leakage, split_summary


def train_baseline(features: pd.DataFrame, config: dict[str, Any], root: Path,
                   synthetic: bool = False) -> dict[str, Any]:
    """Average windows per recording, fit train only and tune threshold on validation."""
    assert_no_leakage(features)
    columns = sorted(c for c in features if c.startswith("f_"))
    development_features = features[features.split.isin(["train", "validation"])].copy()
    if not columns or not np.isfinite(development_features[columns].to_numpy()).all():
        raise ValueError("Missing or nonfinite development feature columns")
    meta = ["subject_id", "subject_group", "recording_id", "dataset_source", "label", "split", "sha256"]
    for field in meta:
        if development_features.groupby("recording_id")[field].nunique().gt(1).any():
            raise ValueError(f"Inconsistent recording metadata: {field}")
    recordings = development_features.groupby(meta)[columns].mean().reset_index()
    if not recordings.label.isin(["Absent", "Present"]).all():
        raise ValueError("Only known binary labels may enter training/evaluation")
    if recordings.groupby("subject_group").label.nunique().gt(1).any():
        raise ValueError("Conflicting participant labels")
    partitions = {name: recordings[recordings.split.eq(name)] for name in ("train", "validation")}
    if any(part.label.nunique() != 2 for part in partitions.values()):
        raise ValueError("Training and validation splits must contain both classes; collect more subjects")
    model = Pipeline([("scaler", StandardScaler()),
                      ("svm", SVC(C=config["svm_c"], gamma=config["svm_gamma"],
                                  class_weight=config["class_weight"], kernel="rbf", probability=False,
                                  random_state=config["seed"]))])
    train = partitions["train"]
    model.fit(train[columns], (train.label == "Present").astype(int))
    output = root / "artifacts"
    for directory in ("models", "metrics", "figures"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"status": "synthetic_smoke_only" if synthetic else "real_data_evaluation",
                              "target": "subject-level murmur Absent=0 vs Present=1; Unknown excluded",
                              "dataset": sorted(recordings.dataset_source.unique()),
                              "feature_count": len(columns), "development_segment_count": len(development_features),
                              "seed": config["seed"], "configuration": config,
                              "development_split_counts": split_summary(recordings[recordings.split.isin(["train", "validation"])]),
                              "python": platform.python_version(), "sklearn": sklearn.__version__,
                              "development_feature_table_sha256": hashlib.sha256(development_features.to_csv(index=False).encode()).hexdigest(),
                              "confidence": "Uncalibrated decision margin; not a probability",
                              "holdout": {"evaluated": False,
                                          "status": config.get("holdout_status", "legacy_exposed"),
                                          "note": "Training does not read holdout labels or scores. Use a new locked external/device holdout for final evaluation."}}
    validation = partitions["validation"]
    validation_scores = model.decision_function(validation[columns])
    threshold_selection = select_screening_threshold(
        validation,
        validation_scores,
        target_sensitivity=config.get("threshold_target_sensitivity", 0.90),
        min_specificity=config.get("threshold_min_specificity", 0.50),
    )
    threshold = threshold_selection["threshold"]
    result["threshold_selection"] = threshold_selection
    result["validation"], predictions = evaluate(validation, validation_scores, threshold)
    predictions.to_csv(output / "metrics/validation_predictions.csv", index=False)
    joblib.dump({"model_kind": "svm", "pipeline": model, "feature_columns": columns,
                 "config": config, "target": result["target"],
                 "decision_threshold": threshold,
                 "threshold_selection": threshold_selection}, output / "models/heart_svm.joblib")
    (output / "metrics/baseline_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    plot_confusion(result["validation"]["subject"]["confusion_matrix"], output / "figures/validation_confusion_matrix.png",
                   title="Validation participants: threshold-selected screening")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/baseline_results.md").write_text(
        "# Heart murmur screening baseline\n\n"
        + ("SYNTHETIC SMOKE TEST ONLY. These numbers are not model performance evidence.\n\n" if synthetic else "Evaluation ran on real CirCor recordings. Research results; no clinical validity claimed.\n\n")
        + "Target: participant murmur Absent versus Present; Unknown excluded, outcome not used. "
        "Linked Additional IDs stay together in deterministic stratified train/validation/test splits. "
        "Preprocessing: mono, 8 kHz polyphase resampling, DC removal, optional filter (see config), "
        "peak normalization, 5-second windows at 50% overlap by default. "
        "MFCC/delta/log-mel/RMS/centroid/ZCR/statistics are averaged over windows per recording. "
        "StandardScaler is fitted on training recordings only, followed by a fixed balanced RBF SVM. "
        "The decision threshold is selected once from linked validation participants, targeting "
        f"sensitivity >= {config.get('threshold_target_sensitivity', 0.90):.2f} with minimum specificity "
        f"{config.get('threshold_min_specificity', 0.50):.2f}. The training command does not evaluate "
        "or reveal a final holdout.\n\n"
        f"```json\n{json.dumps(result, indent=2)}\n```\n\n"
        "Limitations: labels are weak at recording/window level; some sites may have no audible murmur "
        "despite a positive participant label. Recordings contribute equally during training, so "
        "participants with more sites contribute more. The historical local test result was already "
        "inspected and is not a fresh holdout. A newly collected or external locked dataset is required. "
        "No external, prospective, device-transfer or adult-cohort validation. "
        "Decision margins are not calibrated confidence. Quality checks do not establish clinical "
        "interpretability. Any screening result requires clinician review.\n", encoding="utf-8")
    return result
