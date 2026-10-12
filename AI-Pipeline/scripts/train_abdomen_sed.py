"""End-to-end CRNN Sound Event Detection training for Abdomen Bowel Sounds."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401
from auriscore.cnn import prepare_spectrogram_config, require_tensorflow
from auriscore.config import load_config
from auriscore.crnn_sed import build_crnn_sed_model
from auriscore.dataset_abdomen import parse_annotation_file
from auriscore.sed_dataset import create_sed_dataset_iterator
from auriscore.sed_postprocessing import evaluate_event_sed, extract_events_from_curve
from auriscore.spectrogram import spectrogram_shape
from auriscore.visualization import plot_history

LOG = logging.getLogger(__name__)


def train_sed_model(root: Path, config: dict[str, Any], exp_name: str = "EXP-A101-abdomen-crnn-sed") -> dict[str, Any]:
    tf = require_tensorflow()
    root = root.resolve()

    segments_path = root / "data/processed/segments.csv"
    if not segments_path.exists():
        raise FileNotFoundError(
            f"Segments not found at {segments_path}. Run python scripts/preprocess_abdomen_dataset.py first."
        )

    segments = pd.read_csv(segments_path)
    train_segments = segments[segments.split == "train"].reset_index(drop=True)
    val_segments = segments[segments.split == "validation"].reset_index(drop=True)

    if train_segments.empty or val_segments.empty:
        raise ValueError("Train and validation splits must both contain segments")

    # 1. Frequency statistics calculation for per-frequency normalization
    config = prepare_spectrogram_config(train_segments, root, config)

    # 2. Output experiment directory
    exp_dir = root / "results" / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    # 3. Model setup
    freq_bins, time_frames = spectrogram_shape(config)
    input_shape = (freq_bins, time_frames, 1)

    tf.keras.utils.set_random_seed(int(config.get("seed", 42)))
    model = build_crnn_sed_model(input_shape, config)

    batch_size = int(config.get("cnn_batch_size", 16))
    hop_length = int(config.get("hop_length", 128))
    hop_s = hop_length / int(config["sample_rate"])

    # 4. Data pipelines
    def make_gen(frame_subset: pd.DataFrame, is_train: bool):
        rng = np.random.default_rng(int(config.get("seed", 42))) if is_train else None
        def gen():
            yield from create_sed_dataset_iterator(frame_subset, root, config, training=is_train, rng=rng)
        return gen

    sig = (
        tf.TensorSpec(shape=input_shape, dtype=tf.float32),
        tf.TensorSpec(shape=(time_frames, 1), dtype=tf.float32),
    )

    train_ds = (
        tf.data.Dataset.from_generator(make_gen(train_segments, True), output_signature=sig)
        .batch(batch_size)
        .prefetch(tf.data.AUTOTUNE)
    )

    val_ds = (
        tf.data.Dataset.from_generator(make_gen(val_segments, False), output_signature=sig)
        .batch(batch_size)
        .prefetch(tf.data.AUTOTUNE)
    )

    train_steps = max(1, len(train_segments) // batch_size)
    val_steps = max(1, len(val_segments) // batch_size)

    # 5. Training callbacks
    patience = int(config.get("cnn_patience", 8))
    epochs = int(config.get("cnn_epochs", 35))

    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=patience, restore_best_weights=True),
        tf.keras.callbacks.ModelCheckpoint(filepath=str(exp_dir / "best_model.keras"), monitor="val_loss", save_best_only=True),
        tf.keras.callbacks.CSVLogger(filename=str(exp_dir / "history.csv")),
    ]

    print(f"\n======================================================================")
    print(f"  Starting Abdomen CRNN Sound Event Detection (SED) Training")
    print(f"  Experiment : {exp_name}")
    print(f"  Windows    : {len(train_segments)} train, {len(val_segments)} validation")
    print(f"  Resolution : {time_frames} frames per 5.0s window (~{hop_s*1000:.1f} ms/frame)")
    print(f"  Target     : Frame-Level Burst Probability P(t)")
    print(f"======================================================================\n")

    start_time = time.perf_counter()
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        steps_per_epoch=train_steps,
        validation_steps=val_steps,
        epochs=epochs,
        callbacks=callbacks,
        verbose=1,
    )
    duration = time.perf_counter() - start_time

    # 6. Post-training validation & Event-based evaluation
    best_loss = float(min(history.history.get("val_loss", [1.0])))
    stopped_epoch = len(history.history.get("loss", []))

    # Evaluate event detection with collar tolerance on validation windows
    print("\nEvaluating frame-level predictions and event onset/offset intervals...")
    all_val_events_pred: list[dict[str, Any]] = []
    all_val_events_gt: list[dict[str, Any]] = []

    # Iterate through validation windows
    val_iter = create_sed_dataset_iterator(val_segments, root, config, training=False)
    for row, (tensor, mask) in zip(val_segments.to_dict("records"), val_iter, strict=False):
        pred_curve = model.predict(tensor[np.newaxis], verbose=0)[0, :, 0]
        win_start_s = row["start_sample"] / int(config["sample_rate"])

        pred_events = extract_events_from_curve(pred_curve, hop_s=hop_s, window_start_s=win_start_s)
        all_val_events_pred.extend(pred_events)

        # Ground truth events from .txt
        source_path = root / row["file_path"]
        txt_path = source_path.with_suffix(".txt")
        gt_events = [e for e in parse_annotation_file(txt_path) if e.get("is_active", True)]
        # Filter to current window
        win_end_s = win_start_s + (row["window_samples"] / int(config["sample_rate"]))
        gt_in_win = [e for e in gt_events if e["start_sec"] >= win_start_s and e["end_sec"] <= win_end_s]
        all_val_events_gt.extend(gt_in_win)

    # Event-based metrics (DCASE standard: collar = 100 ms)
    event_metrics = evaluate_event_sed(all_val_events_pred, all_val_events_gt, collar_s=0.100)

    # Save summary metrics
    metrics = {
        "status": "completed",
        "experiment_id": exp_name,
        "model_architecture": "CRNN_SED (Conv2D + BiGRU + TimeDistributed)",
        "training_time_s": round(duration, 2),
        "total_epochs": stopped_epoch,
        "best_val_loss": round(best_loss, 4),
        "event_metrics_collar_100ms": event_metrics,
        "detected_events_count": len(all_val_events_pred),
        "ground_truth_events_count": len(all_val_events_gt),
    }

    (exp_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (exp_dir / "status.json").write_text(json.dumps({
        "status": "completed",
        "current_epoch": stopped_epoch,
        "best_val_loss": best_loss,
        "updated_at": time.time(),
    }, indent=2), encoding="utf-8")

    # Plot training curves
    plot_history(history.history, exp_dir / "training_history.png", exp_name)

    print("\n======================================================================")
    print("  CRNN SED Training Completed Successfully!")
    print(f"  Best Val Loss  : {best_loss:.4f} (Epoch {stopped_epoch})")
    print(f"  Detected Events: {len(all_val_events_pred)} (GT: {len(all_val_events_gt)})")
    print(f"  Event F1-Score : {event_metrics['event_f1'] * 100:.2f}% (Collar 100 ms)")
    print(f"  Event Recall   : {event_metrics['recall_sensitivity'] * 100:.2f}%")
    print(f"  Event Precision: {event_metrics['precision'] * 100:.2f}%")
    print(f"  Artifacts      : {exp_dir}")
    print("======================================================================\n")

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Abdomen CRNN Sound Event Detection (SED) model")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/abdomen_sed_crnn.yaml"))
    parser.add_argument("--name", default="EXP-A101-abdomen-crnn-sed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = load_config(config_path)

    train_sed_model(root, config, args.name)


if __name__ == "__main__":
    main()
