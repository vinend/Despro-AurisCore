"""Training and fine-tuning CRNN SED on Kaggle Bowel Sounds Dataset (Nowak et al.).

Experiment: EXP-A104-abdomen-crnn-nowak
Fine-tunes the EXP-A103 pretrained weights on 427 patients + hardware hard-negatives.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import yaml

import _bootstrap  # noqa: F401
from auriscore.cnn import require_tensorflow
from auriscore.crnn_sed import build_crnn_sed_model
from auriscore.sed_postprocessing import evaluate_event_sed, extract_events_from_curve
from auriscore.visualization import plot_history

LOG = logging.getLogger(__name__)


def apply_sed_augmentation(
    mel: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> np.ndarray:
    """Apply safe SED augmentation to a single (40, 126, 1) mel spectrogram:
    - Frequency masking (SpecAugment)
    - Additive Gaussian noise (bounded SNR)
    - Gain/amplitude jitter
    Leaves time alignment and event boundaries 100% intact.
    """
    m = mel.copy()

    # 1. Gain jitter (+/- gain_db)
    gain_db = float(config.get("augmentation_gain_db", 0.0))
    if gain_db > 0:
        factor = float(10.0 ** (rng.uniform(-gain_db, gain_db) / 20.0))
        m *= factor

    # 2. Additive Noise
    if config.get("augmentation_snr_db_min") is not None:
        low = float(config.get("augmentation_snr_db_min", 18.0))
        high = float(config.get("augmentation_snr_db_max", 32.0))
        snr_db = rng.uniform(min(low, high), max(low, high))
        sig_std = float(np.std(m))
        if sig_std > 1e-4:
            noise_std = sig_std / float(10.0 ** (snr_db / 20.0))
            m += rng.normal(0.0, noise_std, size=m.shape).astype(np.float32)

    # 3. Frequency masking (SpecAugment)
    freq_bins = int(config.get("augmentation_freq_mask_bins", 0))
    freq_count = int(config.get("augmentation_freq_mask_count", 1))
    if freq_bins > 0 and freq_count > 0:
        n_freq = m.shape[0]  # 40
        for _ in range(freq_count):
            w = int(rng.integers(1, min(freq_bins, n_freq) + 1))
            f0 = int(rng.integers(0, n_freq - w + 1))
            m[f0 : f0 + w, :, :] = 0.0

    # Clip to normalization limits
    clip_val = float(config.get("spectrogram_normalization_clip", 5.0))
    return np.clip(m, -clip_val, clip_val)


tf_pkg = require_tensorflow()
_BaseDataset = getattr(tf_pkg.keras.utils, "PyDataset", getattr(tf_pkg.keras.utils, "Sequence", object))


class SEDAugmentedSequence(_BaseDataset):
    def __init__(self, X: np.ndarray, y: np.ndarray, batch_size: int, config: dict[str, Any], seed: int = 42, **kwargs):
        super().__init__(**kwargs)
        self.X = X
        self.y = y
        self.batch_size = batch_size
        self.config = config
        self.aug_enabled = bool(config.get("augmentation_enabled", False))
        self.rng = np.random.default_rng(seed)
        self.indices = np.arange(len(X))

    def __len__(self) -> int:
        return int(np.ceil(len(self.X) / float(self.batch_size)))

    def on_epoch_end(self) -> None:
        self.rng.shuffle(self.indices)

    def __getitem__(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        batch_idx = self.indices[idx * self.batch_size : (idx + 1) * self.batch_size]
        batch_x = self.X[batch_idx].copy()
        batch_y = self.y[batch_idx]

        if self.aug_enabled:
            for i in range(len(batch_x)):
                batch_x[i] = apply_sed_augmentation(batch_x[i], self.config, self.rng)

        return batch_x, batch_y


def extract_gt_events_from_mask(mask: np.ndarray, hop_s: float = 0.016) -> list[dict[str, Any]]:
    """Extract discrete ground truth event intervals from a binary 1D mask."""
    events: list[dict[str, Any]] = []
    in_event = False
    start_idx = 0
    for i, val in enumerate(mask):
        if val >= 0.5 and not in_event:
            in_event = True
            start_idx = i
        elif val < 0.5 and in_event:
            in_event = False
            events.append({
                "start_sec": round(start_idx * hop_s, 4),
                "end_sec": round(i * hop_s, 4),
                "duration_sec": round((i - start_idx) * hop_s, 4),
                "label": "BowelSound",
            })
    if in_event:
        events.append({
            "start_sec": round(start_idx * hop_s, 4),
            "end_sec": round(len(mask) * hop_s, 4),
            "duration_sec": round((len(mask) - start_idx) * hop_s, 4),
            "label": "BowelSound",
        })
    return events


def train_nowak_model(
    root: Path,
    config: dict[str, Any],
    exp_name: str = "EXP-A104-abdomen-crnn-nowak",
    eval_only: bool = False,
) -> dict[str, Any]:
    tf = require_tensorflow()
    root = root.resolve()

    manifest_path = root / config.get("segments_path", "data/processed/segments_kaggle.csv")
    tensor_path = root / config.get("tensor_archive", "data/processed/kaggle/kaggle_sed_tensors.npz")

    if not manifest_path.exists() or not tensor_path.exists():
        raise FileNotFoundError(f"Dataset files missing: {manifest_path} or {tensor_path}")

    df_meta = pd.read_csv(manifest_path)
    data = np.load(tensor_path)
    mels_all = data["mels"]  # (N, 40, 126)
    masks_all = data["masks"]  # (N, 126)

    train_idx = df_meta.index[df_meta["split"] == "train"].to_numpy()
    val_idx = df_meta.index[df_meta["split"] == "val"].to_numpy()

    print(f"Loaded dataset: {len(df_meta)} total. Train: {len(train_idx)}, Val: {len(val_idx)}")

    # 1. Per-frequency normalization computed on train split only
    train_mels = mels_all[train_idx]
    mean_freq = np.mean(train_mels, axis=(0, 2), keepdims=True)  # (1, 40, 1)
    std_freq = np.std(train_mels, axis=(0, 2), keepdims=True)  # (1, 40, 1)
    std_freq = np.where(std_freq < 1e-6, 1.0, std_freq)

    clip_val = float(config.get("spectrogram_normalization_clip", 5.0))

    def normalize(mels: np.ndarray) -> np.ndarray:
        norm = (mels - mean_freq) / std_freq
        norm = np.clip(norm, -clip_val, clip_val)
        return norm[..., np.newaxis]  # (N, 40, 126, 1)

    X_train = normalize(train_mels)
    y_train = masks_all[train_idx][..., np.newaxis]  # (N, 126, 1)

    X_val = normalize(mels_all[val_idx])
    y_val = masks_all[val_idx][..., np.newaxis]  # (N, 126, 1)

    # 2. Output directory setup
    exp_dir = root / "results" / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    batch_size = int(config.get("cnn_batch_size", 32))
    pretrained_rel = config.get("pretrained_weights")

    if eval_only:
        print(f"Running in evaluation-only mode for {exp_name}...")
        model_path = exp_dir / "best_model.keras"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")
        model = tf.keras.models.load_model(model_path)
        hist_csv = exp_dir / "history.csv"
        if hist_csv.exists():
            df_hist = pd.read_csv(hist_csv)
            hist_dict = {col: df_hist[col].tolist() for col in df_hist.columns}
            stopped_epoch = len(df_hist)
            best_loss = float(df_hist["val_loss"].min())
            plot_history(hist_dict, exp_dir / "training_history.png", exp_name)
        else:
            stopped_epoch = 0
            best_loss = 0.0
        duration = 0.0
    else:
        # 3. Build CRNN SED Model
        input_shape = (40, 126, 1)
        tf.keras.utils.set_random_seed(int(config.get("seed", 42)))
        model = build_crnn_sed_model(input_shape, config)

        # 4. Transfer Pretrained Weights if specified
        if pretrained_rel:
            pretrained_path = root / pretrained_rel
            if pretrained_path.exists():
                print(f"Loading pretrained weights from {pretrained_path}...")
                orig_m = tf.keras.models.load_model(pretrained_path)
                transferred = 0
                for l_orig in orig_m.layers:
                    w = l_orig.get_weights()
                    if len(w) > 0:
                        try:
                            l_target = model.get_layer(l_orig.name)
                            l_target.set_weights(w)
                            transferred += 1
                        except Exception as ex:
                            LOG.debug("Could not transfer %s: %s", l_orig.name, ex)
                print(f"  Successfully transferred {transferred} layers from EXP-A103!")
            else:
                print(f"Warning: Pretrained weights not found at {pretrained_path}, training from scratch.")

        # 5. Compile with Focal Loss and learning rate for fine-tuning
        lr = float(config.get("cnn_learning_rate", 0.0003))
        gamma = float(config.get("focal_gamma", 2.0))
        alpha = config.get("focal_alpha")
        if alpha is not None:
            loss_fn = tf.keras.losses.BinaryFocalCrossentropy(
                gamma=gamma,
                alpha=float(alpha),
                apply_class_balancing=True,
            )
        else:
            loss_fn = tf.keras.losses.BinaryFocalCrossentropy(gamma=gamma, apply_class_balancing=False)

        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
            loss=loss_fn,
            metrics=[
                tf.keras.metrics.BinaryAccuracy(name="accuracy"),
                tf.keras.metrics.AUC(curve="PR", name="pr_auc"),
                tf.keras.metrics.AUC(curve="ROC", name="roc_auc"),
                tf.keras.metrics.Precision(name="precision"),
                tf.keras.metrics.Recall(name="recall"),
            ],
        )

        # 6. Callbacks
        patience = int(config.get("cnn_patience", 8))
        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=patience,
                mode="min",
                restore_best_weights=True,
                verbose=1,
            ),
            tf.keras.callbacks.ModelCheckpoint(
                filepath=str(exp_dir / "best_model.keras"),
                monitor="val_loss",
                save_best_only=True,
                mode="min",
                verbose=1,
            ),
            tf.keras.callbacks.CSVLogger(str(exp_dir / "history.csv")),
        ]

        # 7. Train
        epochs = int(config.get("cnn_epochs", 40))

        start_t = time.time()
        if config.get("augmentation_enabled", False):
            print("  [Augmentation] Dynamic SED SpecAugment (Freq Mask) + Noise Jitter + Gain enabled on training split.")
            train_seq = SEDAugmentedSequence(X_train, y_train, batch_size, config, seed=int(config.get("seed", 42)))
            history = model.fit(
                train_seq,
                validation_data=(X_val, y_val),
                epochs=epochs,
                callbacks=callbacks,
                verbose=1,
            )
        else:
            history = model.fit(
                X_train,
                y_train,
                validation_data=(X_val, y_val),
                epochs=epochs,
                batch_size=batch_size,
                callbacks=callbacks,
                verbose=1,
            )
        duration = time.time() - start_t
        stopped_epoch = len(history.history["loss"])
        best_loss = min(history.history["val_loss"])

        plot_history(history.history, exp_dir / "training_history.png", exp_name)

    # 8. Event-Based SED Evaluation on Validation Set
    print("\nEvaluating Sound Event Detection on Validation Set...")
    val_preds = model.predict(X_val, batch_size=batch_size, verbose=0)  # (N_val, 126, 1)

    all_val_events_pred: list[dict[str, Any]] = []
    all_val_events_gt: list[dict[str, Any]] = []

    hop_s = 128 / float(config.get("sample_rate", 8000))

    for i in range(len(val_idx)):
        probs = val_preds[i, :, 0]
        gt_mask = y_val[i, :, 0]

        pred_evs = extract_events_from_curve(
            probs,
            hop_s=hop_s,
            window_start_s=0.0,
            onset_threshold=0.55,
            offset_threshold=0.45,
            merge_gap_ms=60.0,
        )
        gt_evs = extract_gt_events_from_mask(gt_mask, hop_s=hop_s)

        # Offset timestamps by window index for global timeline
        w_offset = i * 2.0
        for e in pred_evs:
            e_copy = dict(e)
            e_copy["start_s"] += w_offset
            e_copy["end_s"] += w_offset
            all_val_events_pred.append(e_copy)

        for e in gt_evs:
            e_copy = dict(e)
            e_copy["start_sec"] += w_offset
            e_copy["end_sec"] += w_offset
            all_val_events_gt.append(e_copy)

    event_metrics_100ms = evaluate_event_sed(all_val_events_pred, all_val_events_gt, collar_s=0.100)
    event_metrics_150ms = evaluate_event_sed(all_val_events_pred, all_val_events_gt, collar_s=0.150)
    event_metrics_200ms = evaluate_event_sed(all_val_events_pred, all_val_events_gt, collar_s=0.200)
    event_metrics_250ms = evaluate_event_sed(all_val_events_pred, all_val_events_gt, collar_s=0.250)

    # 9. Comprehensive Sensitivity Evaluation Grid
    print("Running 240-combination sensitivity grid...")
    grid_rows: list[dict[str, Any]] = []
    onset_range = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    collars = [100, 150, 200, 250]
    gaps = [20.0, 40.0, 60.0]

    for onset in onset_range:
        for offset_factor in [0.5, 0.8]:
            offset = round(onset * offset_factor, 3)
            for gap in gaps:
                all_p: list[dict[str, Any]] = []
                for i in range(len(val_idx)):
                    w_offset = i * 2.0
                    pevs = extract_events_from_curve(
                        val_preds[i, :, 0],
                        hop_s=hop_s,
                        onset_threshold=onset,
                        offset_threshold=offset,
                        merge_gap_ms=gap,
                    )
                    for e in pevs:
                        e_c = dict(e)
                        e_c["start_s"] += w_offset
                        e_c["end_s"] += w_offset
                        all_p.append(e_c)

                for c_ms in collars:
                    c_s = c_ms / 1000.0
                    res = evaluate_event_sed(all_p, all_val_events_gt, collar_s=c_s)
                    grid_rows.append({
                        "onset_threshold": onset,
                        "offset_threshold": offset,
                        "merge_gap_ms": gap,
                        "collar_ms": c_ms,
                        "detected_events": len(all_p),
                        "ground_truth_events": len(all_val_events_gt),
                        "true_positives": res["true_positives"],
                        "false_positives": res["false_positives"],
                        "false_negatives": res["false_negatives"],
                        "precision": res["precision"],
                        "recall_sensitivity": res["recall_sensitivity"],
                        "event_f1": res["event_f1"],
                    })

    df_grid = pd.DataFrame(grid_rows)
    df_grid.to_csv(exp_dir / "sensitivity_comprehensive_analysis.csv", index=False)
    with open(exp_dir / "sensitivity_comprehensive_analysis.json", "w", encoding="utf-8") as f:
        json.dump(grid_rows, f, indent=2)

    # 10. Summary Metrics
    metrics = {
        "status": "completed",
        "experiment_id": exp_name,
        "model_architecture": "CRNN_SED (RESIDUAL_SE + BiGRU + TimeDistributed)",
        "pretrained_source": pretrained_rel,
        "dataset": "Kaggle Nowak (427 patients) + AurisCore Hardware Hard Negatives",
        "training_time_s": round(duration, 2),
        "total_epochs": stopped_epoch,
        "best_val_loss": round(best_loss, 4),
        "event_metrics_collar_100ms": event_metrics_100ms,
        "event_metrics_collar_150ms": event_metrics_150ms,
        "event_metrics_collar_200ms": event_metrics_200ms,
        "event_metrics_collar_250ms": event_metrics_250ms,
        "detected_events_count": len(all_val_events_pred),
        "ground_truth_events_count": len(all_val_events_gt),
    }

    (exp_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (exp_dir / "status.json").write_text(
        json.dumps({"experiment_id": exp_name, "status": "completed", "timestamp": time.time()}),
        encoding="utf-8",
    )

    print("\n==================================================")
    print(f"  EXP-A104 Training Completed Successfully!")
    print(f"  Best Val Loss  : {best_loss:.4f} (Epoch {stopped_epoch})")
    print(f"  Detected Events: {len(all_val_events_pred)} (GT: {len(all_val_events_gt)})")
    print(f"  Collar 100ms   : Precision {event_metrics_100ms['precision']:.2%}, Recall {event_metrics_100ms['recall_sensitivity']:.2%}, F1 {event_metrics_100ms['event_f1']:.2%}")
    print(f"  Collar 250ms   : Precision {event_metrics_250ms['precision']:.2%}, Recall {event_metrics_250ms['recall_sensitivity']:.2%}, F1 {event_metrics_250ms['event_f1']:.2%}")
    print("==================================================\n")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/abdomen_sed_nowak.yaml", type=str)
    parser.add_argument("--name", default="EXP-A104-abdomen-crnn-nowak", type=str)
    parser.add_argument("--eval-only", action="store_true", help="Skip training and evaluate existing best_model.keras")
    args = parser.parse_args()

    pipeline_root = Path(__file__).resolve().parent.parent
    cfg_path = pipeline_root / args.config
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    train_nowak_model(pipeline_root, cfg, exp_name=args.name, eval_only=args.eval_only)
