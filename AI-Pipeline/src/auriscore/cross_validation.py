"""Participant-exclusive cross-validation for spectrogram CNN development."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from .cnn import train_cnn
from .evaluation import evaluate, select_screening_threshold
from .splitting import assert_no_leakage
from .visualization import record_experiment


def assign_grouped_folds(
    segments: pd.DataFrame, folds: int, seed: int
) -> pd.DataFrame:
    """Assign one stratified fold per linked participant in development data."""
    development = segments[segments.split.isin(["train", "validation"])].copy()
    subjects = (
        development[["subject_group", "label"]]
        .drop_duplicates()
        .sort_values("subject_group")
        .reset_index(drop=True)
    )
    if subjects.groupby("subject_group").label.nunique().gt(1).any():
        raise ValueError("Linked participants have conflicting labels")
    if subjects.label.value_counts().min() < folds:
        raise ValueError(f"Need at least {folds} development participants in each class")
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    subjects["cv_fold"] = -1
    y = (subjects.label == "Present").to_numpy(dtype=int)
    for fold, (_, validation_indices) in enumerate(
        splitter.split(subjects, y, groups=subjects.subject_group)
    ):
        subjects.loc[validation_indices, "cv_fold"] = fold
    if subjects.cv_fold.lt(0).any():
        raise RuntimeError("Not all development participants received a cross-validation fold")
    return subjects


def cross_validate_cnn(
    segments: pd.DataFrame, config: dict[str, Any], root: Path, synthetic: bool = False
) -> dict[str, Any]:
    """Train grouped folds and select one development threshold from OOF scores."""
    assert_no_leakage(segments)
    folds = int(config.get("cross_validation_folds", 5))
    assignments = assign_grouped_folds(segments, folds, int(config["seed"]))
    output = root / "artifacts/cross_validation"
    output.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(output / "fold_assignments.csv", index=False)

    development = segments[segments.split.isin(["train", "validation"])].copy()
    fold_lookup = assignments.set_index("subject_group").cv_fold
    development["cv_fold"] = development.subject_group.map(fold_lookup).astype(int)
    fold_results: list[dict[str, Any]] = []
    predictions: list[pd.DataFrame] = []
    for fold in range(folds):
        fold_segments = development.copy()
        fold_segments["split"] = np.where(
            fold_segments.cv_fold.eq(fold), "validation", "train"
        )
        fold_config = dict(config, seed=int(config["seed"]) + fold)
        fold_output = output / f"fold_{fold + 1}"
        result = train_cnn(
            fold_segments.drop(columns="cv_fold"),
            fold_config,
            root,
            synthetic=synthetic,
            output_dir=fold_output,
        )
        fold_results.append(
            {
                "fold": fold + 1,
                "training_epochs": result["training_epochs"],
                "best_validation_loss": result["best_validation_loss"],
                "validation": result["validation"],
            }
        )
        predicted = pd.read_csv(fold_output / "metrics/cnn_validation_predictions.csv")
        predicted["cv_fold"] = fold + 1
        predictions.append(predicted)

    out_of_fold = pd.concat(predictions, ignore_index=True)
    if out_of_fold.subject_group.nunique() != assignments.subject_group.nunique():
        raise RuntimeError("Out-of-fold predictions do not cover every development participant")
    threshold_selection = select_screening_threshold(
        out_of_fold,
        out_of_fold.score.to_numpy(),
        target_sensitivity=float(config.get("threshold_target_sensitivity", 0.90)),
        min_specificity=float(config.get("threshold_min_specificity", 0.50)),
    )
    evaluation, _ = evaluate(
        out_of_fold, out_of_fold.score.to_numpy(), threshold_selection["threshold"]
    )
    subject_metric_names = [
        "accuracy",
        "precision",
        "recall_sensitivity",
        "specificity",
        "negative_predictive_value",
        "macro_f1",
        "roc_auc",
        "pr_auc",
        "brier_score",
    ]
    summary_statistics = {}
    for name in subject_metric_names:
        values = [
            item["validation"]["subject"][name]
            for item in fold_results
            if name in item["validation"]["subject"]
        ]
        if not values:
            continue
        summary_statistics[name] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "values": [float(value) for value in values],
        }
    result = {
        "status": "synthetic_cross_validation" if synthetic else "development_cross_validation",
        "fold_count": folds,
        "participant_exclusive": True,
        "threshold_selection": threshold_selection,
        "out_of_fold_evaluation": evaluation,
        "per_fold": fold_results,
        "subject_metric_summary": summary_statistics,
        "holdout": {"evaluated": False, "status": config.get("holdout_status")},
        "warning": "Development-only model selection; not a final or clinical evaluation.",
    }
    out_of_fold.to_csv(output / "out_of_fold_predictions.csv", index=False)
    (output / "cross_validation_metrics.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    report = dict(result, validation=evaluation, model_kind="cnn_spectrogram",
                  evaluation_method="grouped_cross_validation_oof",
                  fold_assignment_sha256=hashlib.sha256(assignments.to_csv(index=False).encode()).hexdigest())
    experiment = record_experiment(root, str(config.get("experiment_name", "cnn-cross-validation")),
                                   config, report, out_of_fold, development)
    result["experiment_id"] = experiment.name
    return result

