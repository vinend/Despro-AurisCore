"""Train-only participant OOF integrity and sensitivity-constrained operating points."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: Path) -> str:
    """Hash an experiment input without opening any other split."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_train_oof(
    predictions: pd.DataFrame,
    assignments: pd.DataFrame,
    train_inventory: pd.DataFrame,
    *,
    expected_sizes: tuple[int, ...] = (114, 114, 114, 113, 113),
) -> None:
    """Prove that each saved prediction is from its participant's outer fold."""
    required = {"participant_id", "label", "probability", "fold"}
    if not required.issubset(predictions) or not {"participant_id", "label", "fold", "role"}.issubset(assignments):
        raise ValueError("Missing required OOF or assignment columns")
    if not {"participant_id", "participant_label"}.issubset(train_inventory):
        raise ValueError("Missing train bag inventory columns")
    expected = len(train_inventory)
    if expected != 568 or len(predictions) != expected:
        raise ValueError("Expected exactly 568 train OOF predictions")
    if predictions.participant_id.duplicated().any() or train_inventory.participant_id.duplicated().any():
        raise ValueError("Duplicate participant")
    if set(predictions.participant_id) != set(train_inventory.participant_id):
        raise ValueError("OOF participant is missing from or outside the train-only inventory")
    if not predictions.label.isin(["Absent", "Present"]).all():
        raise ValueError("Unexpected murmur label")
    if predictions.label.value_counts().to_dict() != {"Absent": 458, "Present": 110}:
        raise ValueError("OOF class counts changed")
    if not np.isfinite(predictions.probability.to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite OOF probability")
    if not predictions.probability.between(0, 1).all():
        raise ValueError("OOF probability outside [0,1]")
    for fold, expected_size in enumerate(expected_sizes, start=1):
        one = assignments.loc[assignments.fold == fold]
        if len(one) != expected or one.participant_id.nunique() != expected:
            raise ValueError(f"Fold {fold} assignment is incomplete")
        if set(one.participant_id) != set(train_inventory.participant_id):
            raise ValueError(f"Fold {fold} contains an outside participant")
        if not one.role.isin(["fit", "early_stop", "outer_eval"]).all():
            raise ValueError(f"Fold {fold} has an unknown role")
        held = one.loc[one.role == "outer_eval"]
        predicted = predictions.loc[predictions.fold == fold]
        if len(held) != expected_size or len(predicted) != expected_size:
            raise ValueError(f"Fold {fold} size mismatch")
        if set(held.participant_id) != set(predicted.participant_id):
            raise ValueError(f"Fold {fold} prediction was trained on its own participant")
    reference = assignments.loc[assignments.role == "outer_eval", ["participant_id", "fold", "label"]]
    joined = predictions.merge(reference, on=["participant_id", "fold"], suffixes=("", "_reference"), validate="one_to_one")
    if len(joined) != expected or not joined.label.eq(joined.label_reference).all():
        raise ValueError("OOF labels or folds disagree with saved assignments")
    inventory = train_inventory[["participant_id", "participant_label"]]
    joined = predictions.merge(inventory, on="participant_id", validate="one_to_one")
    if not joined.label.eq(joined.participant_label).all():
        raise ValueError("OOF labels disagree with train bag inventory")


def threshold_tradeoff(predictions: pd.DataFrame) -> pd.DataFrame:
    """Enumerate every observed score as a threshold; Present is positive."""
    y = predictions.label.eq("Present").to_numpy()
    scores = predictions.probability.to_numpy(dtype=float)
    rows = []
    for threshold in np.unique(scores):
        positive = scores >= threshold
        tp = int(np.count_nonzero(y & positive))
        fn = int(np.count_nonzero(y & ~positive))
        fp = int(np.count_nonzero(~y & positive))
        tn = int(np.count_nonzero(~y & ~positive))
        sensitivity = tp / (tp + fn)
        specificity = tn / (tn + fp)
        precision = tp / (tp + fp) if tp + fp else 0.0
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
        rows.append({
            "threshold": float(threshold),
            "accuracy": (tp + tn) / len(y),
            "precision": precision,
            "sensitivity": sensitivity,
            "specificity": specificity,
            "f1": f1,
            "balanced_accuracy": (sensitivity + specificity) / 2,
            "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        })
    return pd.DataFrame(rows)


def best_at_sensitivity(
    tradeoff: pd.DataFrame,
    target: float,
    *,
    criterion: str = "f1",
) -> dict[str, float | int]:
    """Select by one declared objective, then specificity, precision, threshold."""
    if criterion not in {"f1", "specificity", "precision"}:
        raise ValueError("Unsupported operating-point criterion")
    eligible = tradeoff.loc[tradeoff.sensitivity >= target - 1e-12]
    if eligible.empty:
        raise ValueError(f"No threshold meets sensitivity >= {target}")
    columns = list(dict.fromkeys([criterion, "specificity", "precision", "f1", "threshold"]))
    row = eligible.sort_values(columns, ascending=[False] * len(columns), kind="stable").iloc[0]
    return {key: (int(row[key]) if key in {"tn", "fp", "fn", "tp"} else float(row[key]))
            for key in tradeoff.columns}


def expected_calibration_error(
    labels: np.ndarray,
    probabilities: np.ndarray,
    bins: int = 10,
) -> tuple[float, pd.DataFrame]:
    """Equal-width ECE and reliability data, with each participant counted once."""
    y = np.asarray(labels, dtype=int)
    scores = np.asarray(probabilities, dtype=float)
    if len(y) != len(scores) or not np.isfinite(scores).all() or not np.all((0 <= scores) & (scores <= 1)):
        raise ValueError("Invalid calibration inputs")
    index = np.minimum((scores * bins).astype(int), bins - 1)
    rows = []
    for bin_index in range(bins):
        mask = index == bin_index
        if not np.any(mask):
            continue
        rows.append({
            "bin": bin_index,
            "lower": bin_index / bins,
            "upper": (bin_index + 1) / bins,
            "count": int(mask.sum()),
            "mean_probability": float(scores[mask].mean()),
            "observed_present_fraction": float(y[mask].mean()),
        })
    table = pd.DataFrame(rows)
    ece = float(np.sum(table["count"] * np.abs(
        table["mean_probability"] - table["observed_present_fraction"])) / len(y))
    return ece, table


def fold_zscore_diagnostic(predictions: pd.DataFrame) -> pd.DataFrame:
    """Unlabeled within-fold standardization for audit only; not a deployable calibrator."""
    result = predictions.copy()
    result["probability"] = result.groupby("fold").probability.transform(
        lambda values: (values - values.mean()) / values.std(ddof=1))
    if not np.isfinite(result.probability.to_numpy(dtype=float)).all():
        raise ValueError("Degenerate fold score distribution")
    return result

