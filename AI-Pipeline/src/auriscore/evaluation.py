"""Screening metrics with explicit positive class and independent evaluation units."""
from pathlib import Path
from typing import Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, ConfusionMatrixDisplay


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    """Compute binary screening metrics, Present positive; zero divisions return zero."""
    matrix = confusion_matrix(y, prediction, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    specificity = tn / (tn + fp) if tn + fp else 0.0
    negative_predictive_value = tn / (tn + fn) if tn + fn else 0.0
    return {"accuracy": float(accuracy_score(y, prediction)),
            "precision": float(precision_score(y, prediction, zero_division=0)),
            "recall_sensitivity": float(recall_score(y, prediction, zero_division=0)),
            "specificity": float(specificity),
            "negative_predictive_value": float(negative_predictive_value),
            "macro_f1": float(f1_score(y, prediction, average="macro", labels=[0, 1], zero_division=0)),
            "confusion_matrix": matrix.tolist(),
            "class_counts": {"Absent": int((y == 0).sum()), "Present": int((y == 1).sum())}}


def participant_scores(frame: pd.DataFrame, scores: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach recording scores and average them equally within linked participants."""
    if len(frame) != len(scores):
        raise ValueError("Frame and score lengths differ")
    predictions = frame[["subject_id", "subject_group", "recording_id", "label", "split"]].copy()
    predictions["score"] = np.asarray(scores, dtype=float)
    participants = predictions.groupby("subject_group", as_index=False).agg(
        label=("label", "first"), score=("score", "mean"))
    return predictions, participants


def select_screening_threshold(frame: pd.DataFrame, scores: np.ndarray,
                               target_sensitivity: float = 0.90,
                               min_specificity: float = 0.50) -> dict[str, Any]:
    """Choose a participant threshold on validation data, prioritizing sensitivity."""
    _, participants = participant_scores(frame, scores)
    y = (participants.label == "Present").to_numpy().astype(int)
    if set(y) != {0, 1}:
        raise ValueError("Threshold selection requires both validation classes")
    candidates = np.sort(participants.score.unique())
    evaluated = []
    for threshold in candidates:
        candidate_metrics = metrics(y, (participants.score.to_numpy() >= threshold).astype(int))
        evaluated.append((float(threshold), candidate_metrics))
    sensitivity_candidates = [item for item in evaluated if item[1]["recall_sensitivity"] >= target_sensitivity]
    feasible = [item for item in sensitivity_candidates if item[1]["specificity"] >= min_specificity]
    pool = feasible or sensitivity_candidates
    threshold, selected = max(
        pool,
        key=lambda item: (item[1]["specificity"], item[1]["precision"], item[0]),
    )
    return {
        "threshold": threshold,
        "target_sensitivity": float(target_sensitivity),
        "minimum_specificity": float(min_specificity),
        "constraints_met": bool(feasible),
        "selection_unit": "linked participant mean recording score",
        "validation_subject_metrics": selected,
        "candidate_count": len(evaluated),
    }


def evaluate(frame: pd.DataFrame, scores: np.ndarray, threshold: float = 0.0) -> tuple[dict[str, Any], pd.DataFrame]:
    """Evaluate recording and linked-participant decisions at a locked threshold."""
    predictions, participants = participant_scores(frame, scores)
    predictions["screening_result"] = np.where(predictions.score >= threshold, "murmur present screening", "murmur absent screening")
    result = {"threshold": float(threshold),
              "recording": metrics((predictions.label == "Present").to_numpy().astype(int), (predictions.score >= threshold).to_numpy().astype(int)),
              "subject": metrics((participants.label == "Present").to_numpy().astype(int), (participants.score >= threshold).to_numpy().astype(int)),
              "recording_count": len(predictions), "subject_count": len(participants)}
    return result, predictions


def plot_confusion(matrix: list[list[int]], destination: Path,
                   title: str = "Held-out participants: murmur screening") -> None:
    """Save a participant-level confusion matrix with an explicit partition title."""
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(np.array(matrix), display_labels=["Absent", "Present"]).plot(ax=ax, colorbar=False)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(destination, dpi=140)
    plt.close(fig)
