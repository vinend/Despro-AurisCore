"""Artifact integrity and comparison guards for Heart experiment reports."""
import json

import numpy as np
import pandas as pd
import pytest

from auriscore.evaluation import evaluate
from auriscore.spectrogram import extract_spectrogram_tensor
from auriscore.visualization import plot_examples, plot_history, record_experiment, summarize_best


def _frame() -> pd.DataFrame:
    labels = ["Absent", "Absent", "Present", "Present"]
    rows = []
    for split in ("train", "validation", "test"):
        for index, label in enumerate(labels):
            rows.append({"subject_id": f"{split}-{index}", "subject_group": f"{split}-{index}",
                         "recording_id": f"{split}-{index}", "label": label, "split": split})
    return pd.DataFrame(rows)


def _result(frame: pd.DataFrame, scores: list[float]):
    validation = frame[frame.split.eq("validation")]
    evaluation, predictions = evaluate(validation, np.asarray(scores), threshold=.5)
    return ({"status": "synthetic_smoke_only", "validation": evaluation,
             "threshold_selection": {"threshold": .5}}, predictions)


def test_experiment_artifacts_are_unique_and_comparable(tmp_path):
    frame = _frame()
    config = {"threshold_target_sensitivity": .9, "threshold_min_specificity": .5}
    weak, weak_predictions = _result(frame, [.1, .8, .2, .9])
    strong, strong_predictions = _result(frame, [.1, .2, .8, .9])
    strong["model_kind"] = "cnn_logmel"
    baseline = record_experiment(tmp_path, "baseline", config, weak, weak_predictions, frame)
    best = record_experiment(tmp_path, "cnn", config, strong, strong_predictions, frame)
    assert baseline != best
    assert (baseline / "metrics.json").exists()
    assert not (baseline / "training_history.png").exists()
    assert not (baseline / "roc_curve.png").exists()
    for name in ("class_distribution.png", "confusion_matrix.png",
                 "confusion_matrix_normalized.png", "roc_curve.png",
                 "precision_recall_curve.png", "threshold_analysis.png",
                 "prediction_distribution.png"):
        assert (best / name).stat().st_size > 1000
    assert set(pd.read_csv(best / "class_distribution.csv").split) == {"train", "validation"}
    assert (tmp_path / "results/experiment_comparison.png").exists()
    summary = summarize_best(tmp_path, baseline.name, best.name)
    assert (summary / "baseline_vs_best.png").exists()
    assert json.loads((summary / "selection.json").read_text())["best"] == best.name


def test_summary_rejects_different_evaluation_population(tmp_path):
    frame = _frame()
    result, predictions = _result(frame, [.1, .2, .8, .9])
    first = record_experiment(tmp_path, "first", {}, result, predictions, frame)
    changed = predictions.copy()
    changed.loc[changed.index[0], "subject_group"] = "different-person"
    second = record_experiment(tmp_path, "second", {}, result, changed, frame)
    with pytest.raises(ValueError, match="different validation participants"):
        summarize_best(tmp_path, first.name, second.name)


def test_history_requires_real_accuracy_series(tmp_path):
    destination = tmp_path / "training_history.png"
    plot_history({"loss": [.7], "val_loss": [.8]}, destination, "EXP-H001")
    assert not destination.exists()
    plot_history({"loss": [.7, .5], "val_loss": [.8, .6],
                  "accuracy": [.5, .8], "val_accuracy": [.4, .7]}, destination, "EXP-H001")
    assert destination.stat().st_size > 1000


def test_example_figure_uses_actual_model_tensor(tmp_path, cnn_config):
    cnn_config.update(sample_rate=2000, window_seconds=1.0, n_fft=128,
                      hop_length=32, n_mels=16, feature_fmin=20,
                      feature_fmax=900, spectrogram_cache_enabled=False)
    rows = []
    for index, label in enumerate(("Absent", "Present")):
        signal = np.sin(2 * np.pi * (80 + index * 100) * np.arange(2000) / 2000).astype("float32")
        path = tmp_path / f"{label}.npy"
        np.save(path, signal)
        rows.append({"processed_path": path.name, "start_sample": 0, "valid_samples": 2000,
                     "window_samples": 2000, "recording_id": f"recording-{index}",
                     "label": label, "split": "train"})
    directory = tmp_path / "figures"
    directory.mkdir()
    plot_examples(pd.DataFrame(rows), tmp_path, cnn_config, directory, "EXP-H001")
    assert (directory / "sample_logmel_spectrograms.png").stat().st_size > 1000
    assert (directory / "sample_waveforms.png").stat().st_size > 1000
    with np.load(directory / "sample_tensors.npz") as samples:
        expected = extract_spectrogram_tensor(np.load(tmp_path / "Present.npy"), cnn_config)
        np.testing.assert_allclose(samples["Present"], expected)
