"""Reproducible, participant-level figures for Heart screening experiments."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

from .evaluation import metrics, participant_scores


LABELS = ("Normal / Absent", "Abnormal / Present")
COMPARISON_METRICS = ("f1", "recall_sensitivity", "precision", "balanced_accuracy")


def _save(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def allocate_experiment(root: Path, name: str) -> Path:
    """Reserve the next ID without reusing or overwriting an earlier run."""
    results = root / "results"
    results.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "experiment"
    numbers = [int(match.group(1)) for path in results.iterdir()
               if (match := re.match(r"EXP-H(\d+)-", path.name))]
    number = max(numbers, default=0) + 1
    while True:
        directory = results / f"EXP-H{number:03d}-{slug}"
        try:
            directory.mkdir()
            return directory
        except FileExistsError:
            number += 1


def plot_history(history: dict[str, list[float]], destination: Path, experiment_id: str) -> None:
    """Plot real Keras history; omit this figure if the required series are absent."""
    required = ("loss", "val_loss", "accuracy", "val_accuracy")
    if any(not history.get(key) for key in required):
        return
    epochs = np.arange(1, len(history["loss"]) + 1)
    best = int(np.argmin(history["val_loss"])) + 1
    fig, axes = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    for ax, train, validation, ylabel in (
        (axes[0], "loss", "val_loss", "Loss"),
        (axes[1], "accuracy", "val_accuracy", "Accuracy"),
    ):
        ax.plot(epochs, history[train], label="Train")
        ax.plot(epochs, history[validation], label="Validation")
        ax.axvline(best, color="black", linestyle="--", alpha=.7, label=f"Best epoch {best}")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=.25)
        ax.legend()
    axes[1].set_xlabel("Epoch")
    fig.suptitle(f"{experiment_id} · CNN training history")
    _save(fig, destination)


def plot_confusions(matrix: list[list[int]], directory: Path, title: str) -> None:
    """Save count and row-normalized matrices with explicit class labels."""
    counts = np.asarray(matrix, dtype=int)
    for normalized, filename in ((False, "confusion_matrix.png"), (True, "confusion_matrix_normalized.png")):
        values = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1) if normalized else counts
        fig, ax = plt.subplots(figsize=(7, 6))
        image = ax.imshow(values, cmap="Blues", vmin=0, vmax=1 if normalized else None)
        for row in range(2):
            for column in range(2):
                label = f"{values[row, column]:.1%}\n(n={counts[row, column]})" if normalized else str(counts[row, column])
                ax.text(column, row, label, ha="center", va="center",
                        color="white" if values[row, column] > (0.5 if normalized else counts.max() / 2) else "black")
        ax.set_xticks((0, 1), LABELS)
        ax.set_yticks((0, 1), LABELS)
        ax.set_xlabel("Predicted screening class")
        ax.set_ylabel("Reference class")
        ax.set_title(f"{title} · {'row-normalized' if normalized else 'counts'}")
        fig.colorbar(image, ax=ax, fraction=.046, pad=.04)
        _save(fig, directory / filename)


def _participants(predictions: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    _, participants = participant_scores(predictions, predictions.score.to_numpy(dtype=float))
    return (participants.label.eq("Present").to_numpy(dtype=int),
            participants.score.to_numpy(dtype=float))


def plot_curves(predictions: pd.DataFrame, directory: Path, title: str,
                probability: bool, threshold: float | None = None) -> None:
    """Plot ROC and PR only when both classes and valid continuous scores exist."""
    y, score = _participants(predictions)
    if set(y) != {0, 1} or not np.isfinite(score).all():
        return
    if probability and (np.any(score < 0) or np.any(score > 1)):
        return
    if probability:
        false_positive, true_positive, roc_thresholds = roc_curve(y, score)
        pd.DataFrame({"false_positive_rate": false_positive, "true_positive_rate": true_positive,
                      "threshold": roc_thresholds}).to_csv(directory / "roc_curve.csv", index=False)
        fig, ax = plt.subplots(figsize=(7, 6))
        ax.plot(false_positive, true_positive, label=f"ROC-AUC = {roc_auc_score(y, score):.3f}")
        ax.plot((0, 1), (0, 1), "--", color="gray", label="Random classifier")
        ax.set(xlabel="False positive rate", ylabel="True positive rate", title=f"{title} · participant ROC")
        ax.legend()
        ax.grid(alpha=.25)
        _save(fig, directory / "roc_curve.png")
    precision, recall, pr_thresholds = precision_recall_curve(y, score)
    pd.DataFrame({"recall": recall, "precision": precision,
                  "threshold": np.r_[pr_thresholds, np.nan]}).to_csv(
                      directory / "precision_recall_curve.csv", index=False)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(recall, precision, label=f"Average precision = {average_precision_score(y, score):.3f}")
    ax.axhline(y.mean(), linestyle="--", color="gray", label=f"Prevalence = {y.mean():.3f}")
    if threshold is not None:
        chosen = metrics(y, (score >= threshold).astype(int))
        ax.scatter([chosen["recall_sensitivity"]], [chosen["precision"]], s=75,
                   color="black", zorder=4, label=f"Chosen threshold = {threshold:.3g}")
    ax.set(xlabel="Recall / sensitivity", ylabel="Precision", title=f"{title} · participant precision–recall")
    ax.legend()
    ax.grid(alpha=.25)
    _save(fig, directory / "precision_recall_curve.png")


def plot_prediction_distribution(predictions: pd.DataFrame, threshold: float,
                                 directory: Path, title: str) -> None:
    """Show participant score overlap by reference class."""
    _, participants = participant_scores(predictions, predictions.score.to_numpy(dtype=float))
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, color in (("Absent", "#2878b5"), ("Present", "#cc6b34")):
        values = participants.loc[participants.label.eq(label), "score"].to_numpy(dtype=float)
        if len(values):
            ax.hist(values, bins=min(12, max(3, len(values))), alpha=.55,
                    color=color, label=f"{label} (n={len(values)})")
    ax.axvline(threshold, color="black", linestyle="--", label=f"Threshold = {threshold:.3g}")
    ax.set(xlabel="Participant mean score", ylabel="Count",
           title=f"{title} · prediction distribution")
    ax.legend()
    _save(fig, directory / "prediction_distribution.png")


def plot_thresholds(predictions: pd.DataFrame, threshold: float, directory: Path, title: str) -> None:
    """Document validation-only threshold selection and its trade-offs."""
    if not predictions.split.eq("validation").all():
        raise ValueError("Threshold analysis may use validation predictions only")
    y, score = _participants(predictions)
    rows = []
    for candidate in np.sort(np.unique(score)):
        values = metrics(y, (score >= candidate).astype(int))
        rows.append({"threshold": float(candidate), "f1": values["f1"],
                     "recall_sensitivity": values["recall_sensitivity"],
                     "precision": values["precision"], "specificity": values["specificity"]})
    table = pd.DataFrame(rows)
    table.to_csv(directory / "threshold_analysis.csv", index=False)
    fig, ax = plt.subplots(figsize=(8, 6))
    for key, label in (("f1", "F1"), ("recall_sensitivity", "Recall / sensitivity"),
                       ("precision", "Precision"), ("specificity", "Specificity")):
        ax.plot(table.threshold, table[key], marker=".", label=label)
    ax.axvline(threshold, color="black", linestyle="--", label=f"Chosen = {threshold:.3g}")
    ax.set(xlabel="Validation decision threshold", ylabel="Score", ylim=(-.03, 1.03),
           title=f"{title} · validation threshold analysis")
    ax.legend()
    ax.grid(alpha=.25)
    _save(fig, directory / "threshold_analysis.png")


def plot_class_distribution(frame: pd.DataFrame, directory: Path, title: str,
                            include_test: bool = False) -> None:
    """Count independent participants; keep sealed test labels unseen during training."""
    splits = ("train", "validation", "test") if include_test else ("train", "validation")
    subjects = frame[frame.split.isin(splits)][["split", "subject_group", "label"]].drop_duplicates()
    counts = (subjects.groupby(["split", "label"]).size().unstack(fill_value=0)
              .reindex(index=splits, columns=("Absent", "Present"), fill_value=0))
    counts.to_csv(directory / "class_distribution.csv")
    fig, ax = plt.subplots(figsize=(7, 5))
    positions = np.arange(len(splits))
    for offset, label, color in ((-.2, "Absent", "#2878b5"), (.2, "Present", "#cc6b34")):
        bars = ax.bar(positions + offset, counts[label], width=.4, label=label, color=color)
        ax.bar_label(bars, padding=3)
    ax.set_xticks(positions, [item.title() for item in splits])
    ax.set_ylabel("Independent linked participants")
    ax.set_title(f"{title} · class distribution" + ("" if include_test else " (test sealed)"))
    ax.legend()
    ax.set_ylim(0, max(1, counts.to_numpy().max()) * 1.18)
    _save(fig, directory / "class_distribution.png")


def plot_examples(segments: pd.DataFrame, root: Path, config: dict[str, Any],
                  directory: Path, experiment_id: str) -> None:
    """Render unaugmented numerical tensors from the exact CNN input function."""
    from .cnn import _window

    rows = []
    for label in ("Absent", "Present"):
        candidates = segments[(segments.split == "train") & (segments.label == label)]
        if not candidates.empty:
            rows.append(candidates.iloc[0])
    if not rows:
        return
    tensors = {}
    waveforms = {}
    fig, axes = plt.subplots(len(rows), 1, figsize=(9, 3.4 * len(rows)), squeeze=False)
    for index, row in enumerate(rows):
        audio = np.load(root / row.processed_path, allow_pickle=False)
        start, valid, size = (int(row.start_sample), int(row.valid_samples), int(row.window_samples))
        signal = np.pad(audio[start:start + valid], (0, size - valid))
        tensor = _window(row.to_dict(), root, config, lambda _: audio)[..., 0]
        tensors[str(row.label)] = tensor
        waveforms[str(row.label)] = signal
        ax = axes[index, 0]
        image = ax.imshow(tensor, aspect="auto", origin="lower", cmap="magma")
        ax.set(ylabel="Frequency bin", xlabel="Time frame", title=f"{row.label} · {row.recording_id}")
        fig.colorbar(image, ax=ax, label="Model tensor value")
    fig.suptitle(f"{experiment_id} · actual unaugmented CNN input ({config.get('spectrogram_type', 'logmel')})")
    _save(fig, directory / ("sample_logmel_spectrograms.png" if config.get("spectrogram_type", "logmel") == "logmel" else "sample_spectrograms.png"))
    np.savez_compressed(directory / "sample_tensors.npz", **tensors)
    fig, axes = plt.subplots(len(rows), 1, figsize=(9, 2.8 * len(rows)), squeeze=False)
    for index, row in enumerate(rows):
        signal = waveforms[str(row.label)]
        axes[index, 0].plot(np.arange(len(signal)) / int(config["sample_rate"]), signal, linewidth=.7)
        axes[index, 0].set(xlabel="Time (s)", ylabel="Amplitude", title=f"{row.label} · {row.recording_id}")
    fig.suptitle(f"{experiment_id} · processed waveform before tensor extraction")
    _save(fig, directory / "sample_waveforms.png")


def _comparison_key(config: dict[str, Any], predictions: pd.DataFrame, status: str) -> dict[str, Any]:
    subjects = predictions[["subject_group", "label"]].drop_duplicates().sort_values("subject_group")
    return {"status": status, "target": "Absent=0 Present=1", "unit": "linked participant mean recording score",
            "split": "validation", "subjects": subjects.to_json(orient="records"),
            "selection": [config.get("threshold_target_sensitivity", .9),
                          config.get("threshold_min_specificity", .5)]}


def record_experiment(root: Path, name: str, config: dict[str, Any], result: dict[str, Any],
                      predictions: pd.DataFrame, source: pd.DataFrame,
                      history: dict[str, list[float]] | None = None,
                      examples: pd.DataFrame | None = None,
                      directory: Path | None = None) -> Path:
    """Save one immutable run and refresh comparisons of compatible validation results."""
    directory = directory or allocate_experiment(root, name)
    title = directory.name
    config_data = dict(config)
    (directory / "config.json").write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    payload = dict(result, experiment_id=title,
                   comparison_key=dict(_comparison_key(config, predictions, result["status"]),
                                       evaluation_method=result.get("evaluation_method", "single_validation"),
                                       fold_assignment_sha256=result.get("fold_assignment_sha256")))
    (directory / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    predictions.to_csv(directory / "predictions.csv", index=False)
    if not (directory / "class_distribution.png").exists():
        plot_class_distribution(source, directory, title)
    plot_confusions(result["validation"]["subject"]["confusion_matrix"], directory,
                    f"{title} · validation participants")
    probability = result.get("model_kind", "svm").startswith("cnn")
    threshold = float(result["threshold_selection"]["threshold"])
    plot_curves(predictions, directory, title, probability=probability, threshold=threshold)
    plot_prediction_distribution(predictions, threshold, directory, title)
    plot_thresholds(predictions, threshold, directory, title)
    if history:
        pd.DataFrame(history).assign(epoch=lambda table: np.arange(1, len(table) + 1)).to_csv(
            directory / "history.csv", index=False)
        plot_history(history, directory / "training_history.png", title)
    if examples is not None:
        plot_examples(examples, root, config, directory, title)
    update_comparison(root, directory)
    return directory


def update_comparison(root: Path, current: Path) -> None:
    """Compare only runs with identical participants, labels, selection policy and status."""
    current_data = json.loads((current / "metrics.json").read_text(encoding="utf-8"))
    rows = []
    for path in sorted((root / "results").glob("EXP-H*/metrics.json")):
        if (path.parent / "request.json").exists():
            status_path = path.parent / "status.json"
            if not status_path.exists() or json.loads(status_path.read_text(encoding="utf-8")).get("status") != "completed":
                continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("comparison_key") != current_data["comparison_key"]:
            continue
        subject = data["validation"]["subject"]
        rows.append({"experiment_id": path.parent.name,
                     "f1": subject.get("f1", subject.get("macro_f1")),
                     "recall_sensitivity": subject["recall_sensitivity"],
                     "precision": subject["precision"],
                     "balanced_accuracy": subject["balanced_accuracy"],
                     "accuracy": subject["accuracy"],
                     "roc_auc": subject.get("roc_auc"), "pr_auc": subject.get("pr_auc")})
    if len(rows) < 2:
        return
    table = pd.DataFrame(rows)
    destination = root / "results" / "experiment_comparison.csv"
    table.to_csv(destination, index=False)
    fig, ax = plt.subplots(figsize=(max(9, 1.2 * len(rows) + 5), 6))
    positions = np.arange(len(rows))
    for index, name in enumerate(COMPARISON_METRICS):
        ax.bar(positions + (index - 1.5) * .18, table[name], width=.18,
               label={"f1": "F1", "recall_sensitivity": "Recall / sensitivity",
                      "precision": "Precision", "balanced_accuracy": "Balanced accuracy"}[name])
    ax.set_xticks(positions, table.experiment_id, rotation=30, ha="right")
    ax.set(ylabel="Validation participant score", ylim=(0, 1.05),
           title="Heart screening · comparable validation experiments")
    ax.legend(ncol=2)
    ax.grid(axis="y", alpha=.2)
    _save(fig, root / "results" / "experiment_comparison.png")


def summarize_best(root: Path, baseline_id: str, best_id: str) -> Path:
    """Create a presentation summary only for explicitly chosen comparable runs."""
    paths = [root / "results" / identifier for identifier in (baseline_id, best_id)]
    data = [json.loads((path / "metrics.json").read_text(encoding="utf-8")) for path in paths]
    if data[0]["comparison_key"] != data[1]["comparison_key"]:
        raise ValueError("Baseline and best use different validation participants or evaluation methods")
    if data[1]["validation"]["subject"]["f1"] <= data[0]["validation"]["subject"]["f1"]:
        raise ValueError("Selected best does not improve participant F1 over baseline")
    summary = root / "results" / "summary"
    summary.mkdir(exist_ok=True)
    selection_file = summary / "selection.json"
    if selection_file.exists():
        old = json.loads(selection_file.read_text(encoding="utf-8"))
        if (old.get("baseline"), old.get("best")) != (baseline_id, best_id):
            raise ValueError("Summary already contains a different selection; preserve its artifacts")
    import shutil
    for source, target in (("training_history.png", "best_training_history.png"),
                           ("confusion_matrix.png", "best_confusion_matrix.png"),
                           ("confusion_matrix_normalized.png", "best_confusion_matrix_normalized.png"),
                           ("roc_curve.png", "best_roc_curve.png"),
                           ("precision_recall_curve.png", "best_precision_recall_curve.png")):
        file = paths[1] / source
        if file.exists():
            shutil.copyfile(file, summary / target)
    names = ("accuracy", "precision", "recall_sensitivity", "f1", "balanced_accuracy", "roc_auc", "pr_auc")
    values = pd.DataFrame({"metric": names,
                           "baseline": [data[0]["validation"]["subject"].get(name) for name in names],
                           "best": [data[1]["validation"]["subject"].get(name) for name in names]})
    values.to_csv(summary / "baseline_vs_best.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, 6))
    positions = np.arange(len(names))
    ax.bar(positions - .2, values.baseline, width=.4, label=baseline_id)
    ax.bar(positions + .2, values.best, width=.4, label=best_id)
    ax.set_xticks(positions, ["Accuracy", "Precision", "Recall", "F1", "Balanced\naccuracy", "ROC-AUC", "PR-AUC"])
    ax.set(ylabel="Validation participant score", ylim=(0, 1.05),
           title="Baseline vs selected best · identical validation evaluation")
    ax.legend()
    ax.grid(axis="y", alpha=.2)
    _save(fig, summary / "baseline_vs_best.png")
    (summary / "selection.json").write_text(json.dumps({"baseline": baseline_id, "best": best_id,
        "evaluation_split": "validation", "comparison_key": data[0]["comparison_key"]}, indent=2), encoding="utf-8")
    return summary


def record_final_holdout(root: Path, result: dict[str, Any], predictions: pd.DataFrame,
                         source: pd.DataFrame) -> Path:
    """Save sealed-test plots after the one-time evaluation has completed."""
    results = root / "results"
    results.mkdir(parents=True, exist_ok=True)
    directory = results / f"final-holdout-{result['holdout_identity_sha256'][:12]}"
    if directory.exists():
        raise FileExistsError(f"Final holdout report already exists: {directory}")
    with tempfile.TemporaryDirectory(dir=results, prefix=".holdout-") as temporary:
        draft = Path(temporary)
        (draft / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        predictions.to_csv(draft / "predictions.csv", index=False)
        title = "Final locked holdout participants"
        plot_confusions(result["subject"]["confusion_matrix"], draft, title)
        plot_curves(predictions, draft, title,
                    probability=result.get("model_kind", "svm").startswith("cnn"),
                    threshold=float(result["threshold"]))
        plot_prediction_distribution(predictions, float(result["threshold"]), draft, title)
        plot_class_distribution(source, draft, title, include_test=True)
        draft.rename(directory)
    return directory
