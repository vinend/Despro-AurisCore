"""Read-only development diagnostics. Never fit weights or open holdout labels."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .acquisition_lung import digest
from .lung_training import preflight


def score_summary(truth: np.ndarray, scores: np.ndarray, mask: np.ndarray,
                  classes: list[str], thresholds: list[float]) -> dict:
    """Describe saved scores at existing thresholds without selecting new ones."""
    if (truth.shape != scores.shape or mask.shape != truth.shape or truth.ndim != 2
            or truth.shape[1] != len(classes) or len(thresholds) != len(classes)
            or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1))
            or not np.isin(truth, [0, 1]).all() or not np.isin(mask, [0, 1]).all()
            or not np.isfinite(thresholds).all() or np.any((np.array(thresholds) < 0) | (np.array(thresholds) > 1))):
        raise ValueError("Invalid development predictions")
    result = {}
    for i, label in enumerate(classes):
        valid = mask[:, i] > 0
        y, p = truth[valid, i].astype(bool), scores[valid, i]
        positives = int(y.sum())
        prevalence = float(y.mean()) if len(y) else None
        distributions = {}
        for name, selected in (("positive", p[y]), ("negative", p[~y])):
            distributions[name] = {
                "count": len(selected),
                "mean": float(selected.mean()) if len(selected) else None,
                "quantiles_05_25_50_75_95": np.quantile(selected, [.05, .25, .5, .75, .95]).tolist() if len(selected) else [],
                "histogram_10_bins_0_to_1": np.histogram(selected, bins=np.linspace(0, 1, 11))[0].tolist(),
            }
        predicted = p >= thresholds[i]
        tp, fp, fn = int((predicted & y).sum()), int((predicted & ~y).sum()), int((~predicted & y).sum())
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
        baseline = 2 * positives / (len(y) + positives) if len(y) + positives else None
        result[label] = {"valid_frames": len(y), "positive_prevalence": prevalence,
                         "saved_threshold": thresholds[i], "predicted_positive_fraction": float(predicted.mean()) if len(y) else None,
                         "f1": f1, "always_positive_f1": baseline,
                         "f1_gain_over_always_positive": f1 - baseline if f1 is not None and baseline is not None else None,
                         "score_distributions": distributions}
    if {"inhalation", "exhalation"}.issubset(classes):
        i, e = classes.index("inhalation"), classes.index("exhalation")
        valid = (mask[:, i] > 0) & (mask[:, e] > 0)
        result["phase_joint"] = {
            "jointly_valid_frames": int(valid.sum()),
            "truth_both_positive": int(((truth[:, i] > 0) & (truth[:, e] > 0) & valid).sum()),
            "predicted_both_positive": int(((scores[:, i] >= thresholds[i]) & (scores[:, e] >= thresholds[e]) & valid).sum()),
            "predicted_neither_positive": int(((scores[:, i] < thresholds[i]) & (scores[:, e] < thresholds[e]) & valid).sum()),
        }
    return result


def diagnose(cache: Path, audit: Path, *, experiment: Path | None = None) -> dict:
    """Audit complete TRAIN/validation caches and optional bound saved predictions.

    Counts include overlapping windows, matching the development evaluator.
    Class weights are reconstructed from TRAIN only. No model is loaded.
    """
    config, index = preflight(cache, audit)
    classes = config["classes"]
    recordings = pd.read_csv(audit.parent / "recordings.csv", dtype={"group": str})
    development = recordings[recordings.split.isin(["train", "validation"])].copy()
    if development.recording_id.duplicated().any():
        raise ValueError("Duplicate development identities")
    metadata = development.set_index("recording_id")
    if not set(index.recording_id).issubset(metadata.index):
        raise ValueError("Cache contains non-development identities")
    events = pd.read_csv(audit.parent / "events.csv")
    events = events[events.recording_id.isin(metadata.index)].copy()
    durations = {}
    for label in classes:
        values = (events.loc[events.label == label, "end_s"] - events.loc[events.label == label, "start_s"]).to_numpy()
        durations[label] = {"events": len(values), "duration_quantiles_05_50_95_s": np.quantile(values, [.05, .5, .95]).tolist() if len(values) else []}
    totals = {}
    device_totals = {}
    violations = {"supervised_tail_frames": 0, "masked_positive_cells": 0}
    phase = {}
    for row in index.itertuples():
        record = metadata.loc[row.recording_id]
        if record.split != row.split or str(record.group) != str(row.group):
            raise ValueError("Cache/manifest partition mismatch")
        with np.load(cache / row.file, allow_pickle=False) as block:
            y, m, times = (block[key] for key in ("targets", "mask", "times_s"))
            if (y.ndim != 2 or y.shape != m.shape or y.shape[1] != len(classes)
                    or times.shape != (len(y),) or not np.isfinite(times).all()
                    or not np.isin(y, [0, 1]).all() or not np.isin(m, [0, 1]).all()):
                raise ValueError("Malformed diagnostic cache block")
            positives, valid = (y * m).sum(axis=0).astype(np.int64), m.sum(axis=0).astype(np.int64)
            for container, key in ((totals, row.split), (device_totals, f"{row.split}/{record.device}")):
                if key not in container:
                    container[key] = {"windows": 0, "frames": 0, "positive": np.zeros(len(classes), dtype=np.int64), "valid": np.zeros(len(classes), dtype=np.int64)}
                container[key]["windows"] += 1
                container[key]["frames"] += len(y)
                container[key]["positive"] += positives
                container[key]["valid"] += valid
            ends = times + config["n_fft"] / (2 * config["sample_rate"])
            violations["supervised_tail_frames"] += int(((ends > record.valid_end_s + 1e-9) & np.any(m > 0, axis=1)).sum())
            # Positives may legitimately be masked in padded frames; count, do not call a defect.
            violations["masked_positive_cells"] += int(((y > 0) & (m == 0)).sum())
            if {"inhalation", "exhalation"}.issubset(classes):
                i, e = classes.index("inhalation"), classes.index("exhalation")
                joint = (m[:, i] > 0) & (m[:, e] > 0)
                state = phase.setdefault(row.split, {"jointly_valid": 0, "both_positive": 0, "neither_positive": 0})
                state["jointly_valid"] += int(joint.sum())
                state["both_positive"] += int(((y[:, i] > 0) & (y[:, e] > 0) & joint).sum())
                state["neither_positive"] += int(((y[:, i] == 0) & (y[:, e] == 0) & joint).sum())
    training = totals["train"]
    weights = np.clip((training["valid"] - training["positive"]) / np.maximum(training["positive"], 1), .25, 20)

    def summarize(values: dict) -> dict:
        output = {}
        for key, counts in values.items():
            rows = {}
            for i, label in enumerate(classes):
                positive, valid = int(counts["positive"][i]), int(counts["valid"][i])
                rows[label] = {"positive": positive, "negative": valid - positive, "masked": counts["frames"] - valid,
                               "positive_prevalence": positive / valid if valid else None,
                               "always_positive_f1": 2 * positive / (valid + positive) if valid + positive else None}
            output[key] = {"windows": counts["windows"], "classes": rows}
        return output

    report = {"schema_version": "lung-diagnostics-v1", "role": "development_only",
              "training_started": False, "official_test_labels_opened": False,
              "counting_unit": "cached_frames_including_overlapping_windows",
              "index_sha256": digest(cache / "index.csv"), "audit_sha256": digest(audit),
              "classes": classes, "splits": summarize(totals), "devices": summarize(device_totals),
              "train_positive_weights": dict(zip(classes, weights.tolist())),
              "phase_target_states": phase, "mask_checks": violations, "annotation_durations": durations,
              "saved_predictions": None}
    if experiment is not None:
        source = json.loads((experiment / "source.json").read_text())
        if (source.get("evaluation_role") != "development_only" or source.get("config") != config
                or source.get("index_sha256") != report["index_sha256"]
                or source.get("audit_sha256") != report["audit_sha256"]):
            raise ValueError("Experiment is not a development run bound to this cache")
        report["saved_predictions"] = {}
        for folder in sorted(experiment.glob("fold-*")):
            evaluation = json.loads((folder / "evaluation.json").read_text())
            if evaluation.get("role") != "development_only" or evaluation.get("classes") != classes:
                raise ValueError("Invalid development evaluation role/classes")
            path = folder / "development_predictions.npz"
            with np.load(path, allow_pickle=False) as saved:
                report["saved_predictions"][folder.name] = {
                    "sha256": digest(path),
                    "summary": score_summary(saved["truth"], saved["scores"], saved["mask"], classes, evaluation["thresholds"])}
        if not report["saved_predictions"]:
            raise ValueError("No saved development predictions")
    return report
