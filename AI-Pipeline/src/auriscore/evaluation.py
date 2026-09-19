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
    return {"accuracy": float(accuracy_score(y, prediction)),
            "precision": float(precision_score(y, prediction, zero_division=0)),
            "recall_sensitivity": float(recall_score(y, prediction, zero_division=0)),
            "macro_f1": float(f1_score(y, prediction, average="macro", labels=[0, 1], zero_division=0)),
            "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
            "class_counts": {"Absent": int((y == 0).sum()), "Present": int((y == 1).sum())}}


def evaluate(frame: pd.DataFrame, scores: np.ndarray) -> tuple[dict[str, Any], pd.DataFrame]:
    """Average recording decision margins equally within each linked participant."""
    predictions = frame[["subject_id", "subject_group", "recording_id", "label", "split"]].copy()
    predictions["decision_margin"] = scores
    predictions["screening_result"] = np.where(scores >= 0, "murmur present screening", "murmur absent screening")
    participants = predictions.groupby("subject_group").agg(label=("label", "first"), decision_margin=("decision_margin", "mean"))
    result = {"recording": metrics((predictions.label == "Present").to_numpy().astype(int), (scores >= 0).astype(int)),
              "subject": metrics((participants.label == "Present").to_numpy().astype(int), (participants.decision_margin >= 0).to_numpy().astype(int)),
              "recording_count": len(predictions), "subject_count": len(participants)}
    return result, predictions


def plot_confusion(matrix: list[list[int]], destination: Path) -> None:
    """Save participant-level held-out confusion matrix."""
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(np.array(matrix), display_labels=["Absent", "Present"]).plot(ax=ax, colorbar=False)
    ax.set_title("Held-out participants: murmur screening")
    fig.tight_layout()
    fig.savefig(destination, dpi=140)
    plt.close(fig)
