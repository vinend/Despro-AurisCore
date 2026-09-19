"""Fixed SVM baseline with training-only scaling and untouched final holdout."""
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
from .evaluation import evaluate, plot_confusion
from .splitting import assert_no_leakage, split_summary


def train_baseline(features: pd.DataFrame, config: dict[str, Any], root: Path,
                   synthetic: bool = False) -> dict[str, Any]:
    """Average window features per recording, fit train only, evaluate val then test."""
    assert_no_leakage(features)
    columns = sorted(c for c in features if c.startswith("f_"))
    if not columns or not np.isfinite(features[columns].to_numpy()).all():
        raise ValueError("Missing or nonfinite feature columns")
    meta = ["subject_id", "subject_group", "recording_id", "dataset_source", "label", "split", "sha256"]
    for field in meta:
        if features.groupby("recording_id")[field].nunique().gt(1).any():
            raise ValueError(f"Inconsistent recording metadata: {field}")
    recordings = features.groupby(meta)[columns].mean().reset_index()
    if not recordings.label.isin(["Absent", "Present"]).all():
        raise ValueError("Only known binary labels may enter training/evaluation")
    if recordings.groupby("subject_group").label.nunique().gt(1).any():
        raise ValueError("Conflicting participant labels")
    partitions = {name: recordings[recordings.split.eq(name)] for name in ("train", "validation", "test")}
    if any(part.label.nunique() != 2 for part in partitions.values()):
        raise ValueError("Every split must contain both classes; collect more subjects")
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
                              "feature_count": len(columns), "segment_count": len(features),
                              "seed": config["seed"], "configuration": config,
                              "split_counts": split_summary(recordings),
                              "python": platform.python_version(), "sklearn": sklearn.__version__,
                              "feature_table_sha256": hashlib.sha256(features.to_csv(index=False).encode()).hexdigest(),
                              "confidence": "Uncalibrated decision margin; not a probability"}
    # No tuning or refitting after validation; the fixed model sees test only here.
    for name in ("validation", "test"):
        part = partitions[name]
        result[name], predictions = evaluate(part, model.decision_function(part[columns]))
        predictions.to_csv(output / f"metrics/{name}_predictions.csv", index=False)
    joblib.dump({"pipeline": model, "feature_columns": columns, "config": config,
                 "target": result["target"]}, output / "models/heart_svm.joblib")
    (output / "metrics/baseline_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    plot_confusion(result["test"]["subject"]["confusion_matrix"], output / "figures/confusion_matrix.png")
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
        "No hyperparameter search or test-based selection was performed. "
        "Participant decisions use the mean recording margin at threshold zero.\n\n"
        f"```json\n{json.dumps(result, indent=2)}\n```\n\n"
        "Limitations: labels are weak at recording/window level; some sites may have no audible murmur "
        "despite a positive participant label. Recordings contribute equally during training, so "
        "participants with more sites contribute more. These local holdouts are not the official "
        "Challenge hidden test. No external, prospective, device-transfer or adult-cohort validation. "
        "Decision margins are not calibrated confidence. Quality checks do not establish clinical "
        "interpretability. Any screening result requires clinician review.\n", encoding="utf-8")
    return result
