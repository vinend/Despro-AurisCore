"""Evaluate SED Onset Threshold, Offset, Merge Gap, and Collar Tolerance Sensitivity for Abdomen CRNN."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401
from auriscore.cnn import require_tensorflow
from auriscore.dataset_abdomen import parse_annotation_file
from auriscore.sed_dataset import create_sed_dataset_iterator
from auriscore.sed_postprocessing import evaluate_event_sed, extract_events_from_curve

LOG = logging.getLogger(__name__)


def run_comprehensive_sensitivity_analysis(
    root: Path,
    exp_dir: Path,
) -> pd.DataFrame:
    tf = require_tensorflow()
    root = root.resolve()
    exp_dir = exp_dir.resolve()

    config_path = exp_dir / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found at {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    model_path = exp_dir / "best_model.keras"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found at {model_path}")
    print(f"Loading trained CRNN SED model from {model_path}...")
    model = tf.keras.models.load_model(str(model_path), compile=False)

    segments_path = root / "data/processed/segments.csv"
    segments = pd.read_csv(segments_path)
    val_segments = segments[segments.split == "validation"].reset_index(drop=True)
    print(f"Loaded {len(val_segments)} validation segments.")

    hop_length = int(config.get("hop_length", 128))
    hop_s = hop_length / int(config["sample_rate"])

    # 1. Run inference once and collect ground-truth & predicted curves
    print("Running validation inference (caching prediction curves)...")
    val_iter = create_sed_dataset_iterator(val_segments, root, config, training=False)
    cached_windows: list[dict[str, Any]] = []

    for row, (tensor, mask) in zip(val_segments.to_dict("records"), val_iter, strict=False):
        pred_curve = model.predict(tensor[np.newaxis], verbose=0)[0, :, 0]
        win_start_s = row["start_sample"] / int(config["sample_rate"])
        win_end_s = win_start_s + (row["window_samples"] / int(config["sample_rate"]))

        # Ground truth
        source_path = root / row["file_path"]
        txt_path = source_path.with_suffix(".txt")
        gt_events = [e for e in parse_annotation_file(txt_path) if e.get("is_active", True)]
        gt_in_win = [e for e in gt_events if e["start_sec"] >= win_start_s and e["end_sec"] <= win_end_s]

        cached_windows.append({
            "pred_curve": pred_curve,
            "win_start_s": win_start_s,
            "gt_events": gt_in_win,
        })

    total_gt = sum(len(w["gt_events"]) for w in cached_windows)
    print(f"Cached {len(cached_windows)} windows with {total_gt} total ground-truth burst events.\n")

    # 2. Grid evaluation
    onset_thresholds = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    collars_s = [0.100, 0.150, 0.200, 0.250]
    merge_gaps_ms = [20.0, 40.0, 60.0]

    results: list[dict[str, Any]] = []

    for onset_th in onset_thresholds:
        # Test 2 offset schemes: tight hysteresis (onset - 0.10) and loose (onset * 0.5)
        offset_options = [
            round(max(0.10, onset_th - 0.10), 3),
            round(max(0.10, onset_th * 0.5), 3),
        ]
        # Deduplicate
        offset_options = sorted(list(set(offset_options)))

        for offset_th in offset_options:
            if offset_th >= onset_th:
                continue

            for merge_gap in merge_gaps_ms:
                all_pred_events: list[dict[str, Any]] = []
                all_gt_events: list[dict[str, Any]] = []

                for w in cached_windows:
                    evs = extract_events_from_curve(
                        w["pred_curve"],
                        hop_s=hop_s,
                        window_start_s=w["win_start_s"],
                        onset_threshold=onset_th,
                        offset_threshold=offset_th,
                        min_duration_ms=25.0,
                        merge_gap_ms=merge_gap,
                    )
                    all_pred_events.extend(evs)
                    all_gt_events.extend(w["gt_events"])

                for collar in collars_s:
                    metrics = evaluate_event_sed(all_pred_events, all_gt_events, collar_s=collar)
                    results.append({
                        "onset_threshold": onset_th,
                        "offset_threshold": offset_th,
                        "merge_gap_ms": merge_gap,
                        "collar_ms": int(collar * 1000),
                        "detected_events": len(all_pred_events),
                        "ground_truth_events": len(all_gt_events),
                        "true_positives": int(metrics["true_positives"]),
                        "false_positives": int(metrics["false_positives"]),
                        "false_negatives": int(metrics["false_negatives"]),
                        "precision": metrics["precision"],
                        "recall_sensitivity": metrics["recall_sensitivity"],
                        "event_f1": metrics["event_f1"],
                    })

    df_results = pd.DataFrame(results)

    # Save to disk
    csv_path = exp_dir / "sensitivity_comprehensive_analysis.csv"
    json_path = exp_dir / "sensitivity_comprehensive_analysis.json"
    df_results.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Results saved to {csv_path} and {json_path}\n")

    return df_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SED comprehensive sensitivity")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--exp-dir", type=Path, default=Path("results/EXP-A101-abdomen-crnn-sed"))
    args = parser.parse_args()

    root = args.root.resolve()
    exp_dir = args.exp_dir if args.exp_dir.is_absolute() else root / args.exp_dir

    df = run_comprehensive_sensitivity_analysis(root, exp_dir)

    print("\n=== TOP 15 BY EVENT F1-SCORE ===")
    top_f1 = df.sort_values(by="event_f1", ascending=False).head(15)
    print(top_f1[["onset_threshold", "offset_threshold", "merge_gap_ms", "collar_ms", "detected_events", "true_positives", "false_positives", "precision", "recall_sensitivity", "event_f1"]].to_string(index=False))

    print("\n=== TOP 15 BY RECALL / SENSITIVITY (WITH PRECISION >= 0.30) ===")
    top_rec = df[df["precision"] >= 0.30].sort_values(by="recall_sensitivity", ascending=False).head(15)
    print(top_rec[["onset_threshold", "offset_threshold", "merge_gap_ms", "collar_ms", "detected_events", "true_positives", "false_positives", "precision", "recall_sensitivity", "event_f1"]].to_string(index=False))

    print("\n=== SENSITIVITY ON COLLAR = 100 ms (Standard DCASE) ===")
    dcase_100 = df[df["collar_ms"] == 100].sort_values(by="event_f1", ascending=False).head(10)
    print(dcase_100[["onset_threshold", "offset_threshold", "merge_gap_ms", "detected_events", "true_positives", "false_positives", "precision", "recall_sensitivity", "event_f1"]].to_string(index=False))


if __name__ == "__main__":
    main()
