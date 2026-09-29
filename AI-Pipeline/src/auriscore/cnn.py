"""Optional TensorFlow CNN over log-mel windows with participant-aware weighting."""
from __future__ import annotations

import hashlib
import json
import math
import platform
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .augmentation import augment_spectrogram, augment_waveform, cutmix, mixup
from .evaluation import evaluate, plot_confusion, select_screening_threshold
from .spectrogram import extract_spectrogram_tensor, spectrogram_shape
from .spectrogram_cache import load_or_create
from .splitting import assert_no_leakage, split_summary


META_COLUMNS = ["subject_id", "subject_group", "recording_id", "dataset_source", "label", "split", "sha256"]


def require_tensorflow() -> Any:
    """Import TensorFlow lazily so the SVM installation stays lightweight."""
    try:
        import tensorflow as tf
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError(
            "CNN training requires TensorFlow. Install requirements-cnn.txt in the AI-Pipeline environment."
        ) from exc
    return tf


def build_cnn_model(input_shape: tuple[int, int, int], config: dict[str, Any]) -> Any:
    """Build either the reproducible compact baseline or a residual SE-CNN."""
    tf = require_tensorflow()
    inputs = tf.keras.Input(shape=input_shape, name="spectrogram")
    x = inputs
    architecture = str(config.get("cnn_architecture", "compact"))
    if architecture == "compact":
        for filters in (16, 32, 64):
            x = tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False)(x)
            x = tf.keras.layers.BatchNormalization()(x)
            x = tf.keras.layers.Activation("relu")(x)
            x = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    elif architecture == "residual_se":
        filters_sequence = tuple(int(value) for value in config.get("cnn_filters", [24, 48, 96]))
        ratio = max(2, int(config.get("cnn_se_ratio", 8)))
        x = tf.keras.layers.Conv2D(filters_sequence[0], 3, padding="same", use_bias=False)(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.Activation("relu")(x)
        for block_index, filters in enumerate(filters_sequence):
            shortcut = x
            x = tf.keras.layers.SeparableConv2D(filters, 3, padding="same", use_bias=False)(x)
            x = tf.keras.layers.BatchNormalization()(x)
            x = tf.keras.layers.Activation("relu")(x)
            x = tf.keras.layers.SeparableConv2D(filters, 3, padding="same", use_bias=False)(x)
            x = tf.keras.layers.BatchNormalization()(x)
            if int(shortcut.shape[-1]) != filters:
                shortcut = tf.keras.layers.Conv2D(filters, 1, padding="same", use_bias=False)(shortcut)
                shortcut = tf.keras.layers.BatchNormalization()(shortcut)
            x = tf.keras.layers.Add()([x, shortcut])
            x = tf.keras.layers.Activation("relu")(x)
            squeeze = tf.keras.layers.GlobalAveragePooling2D(keepdims=True)(x)
            squeeze = tf.keras.layers.Conv2D(max(4, filters // ratio), 1, activation="relu")(squeeze)
            squeeze = tf.keras.layers.Conv2D(filters, 1, activation="sigmoid")(squeeze)
            x = tf.keras.layers.Multiply()([x, squeeze])
            if block_index < len(filters_sequence) - 1:
                x = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    else:  # load_config normally catches this, but direct library use should fail clearly.
        raise ValueError(f"Unsupported cnn_architecture: {architecture}")
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(float(config.get("cnn_dropout", 0.30)))(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="murmur_probability")(x)
    model = tf.keras.Model(inputs, outputs, name=f"auriscore_heart_{architecture}_cnn")
    loss_name = str(config.get("cnn_loss", "binary_crossentropy"))
    if loss_name == "focal":
        loss = tf.keras.losses.BinaryFocalCrossentropy(
            gamma=float(config.get("cnn_focal_gamma", 2.0)),
            apply_class_balancing=False,
        )
    elif loss_name == "binary_crossentropy":
        loss = tf.keras.losses.BinaryCrossentropy(
            label_smoothing=float(config.get("cnn_label_smoothing", 0.0))
        )
    else:
        raise ValueError("cnn_loss must be binary_crossentropy or focal")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(float(config.get("cnn_learning_rate", 1e-3))),
        loss=loss,
        metrics=[
            tf.keras.metrics.Recall(name="sensitivity"),
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.AUC(name="roc_auc"),
            tf.keras.metrics.AUC(name="pr_auc", curve="PR"),
        ],
    )
    return model


def _window(
    row: dict[str, Any],
    root: Path,
    config: dict[str, Any],
    loader: Any,
    training: bool = False,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    if config.get("spectrogram_cache_enabled", False) and not training:
        tensor, _, _ = load_or_create(row, root, config, loader)
        return tensor[..., np.newaxis]
    audio = loader(str(root / row["processed_path"]))
    start = int(row["start_sample"])
    valid = int(row["valid_samples"])
    size = int(row["window_samples"])
    signal = np.pad(audio[start:start + valid], (0, size - valid))
    if training:
        if rng is None:
            raise ValueError("Training augmentation requires a random generator")
        signal = augment_waveform(signal, config, rng)
    tensor = extract_spectrogram_tensor(signal, config)
    if training:
        tensor = augment_spectrogram(tensor, config, rng)
    return tensor[..., np.newaxis]


def _participant_weights(frame: pd.DataFrame) -> np.ndarray:
    """Give every participant equal total weight, then balance the two classes."""
    subject_labels = frame[["subject_group", "label"]].drop_duplicates()
    class_subjects = subject_labels.label.value_counts()
    if set(class_subjects.index) != {"Absent", "Present"}:
        raise ValueError("CNN partition must contain both classes")
    class_weights = len(subject_labels) / (2.0 * class_subjects)
    windows_per_subject = frame.subject_group.value_counts()
    weights = frame.apply(
        lambda row: class_weights[row.label] / windows_per_subject[row.subject_group], axis=1
    ).to_numpy(dtype=np.float32)
    return weights / weights.mean()


def _example_iterator(
    frame: pd.DataFrame,
    root: Path,
    config: dict[str, Any],
    include_weights: bool,
    training: bool = False,
    rng: np.random.Generator | None = None,
) -> Iterator[Any]:
    @lru_cache(maxsize=32)
    def loader(path: str) -> np.ndarray:
        return np.load(path, allow_pickle=False)

    if training and rng is None:
        rng = np.random.default_rng(int(config["seed"]))
    records = frame.to_dict("records")
    weights = _participant_weights(frame) if include_weights else np.ones(len(frame), dtype=np.float32)
    mix_probability = float(config.get("mixup_probability", 0.0))
    cut_probability = float(config.get("cutmix_probability", 0.0))
    for row_index, (row, weight) in enumerate(zip(records, weights, strict=True)):
        tensor = _window(row, root, config, loader, training=training, rng=rng)
        label = np.float32(row["label"] == "Present")
        if training and rng is not None and len(records) > 1:
            draw = float(rng.random())
            if draw < mix_probability + cut_probability:
                partner_index = int(rng.integers(0, len(records) - 1))
                if partner_index >= row_index:
                    partner_index += 1
                partner = records[partner_index]
                partner_tensor = _window(
                    partner, root, config, loader, training=True, rng=rng
                )
                partner_label = np.float32(partner["label"] == "Present")
                if draw < mix_probability:
                    tensor, label, retained = mixup(
                        tensor,
                        float(label),
                        partner_tensor,
                        float(partner_label),
                        float(config.get("mixup_alpha", 0.2)),
                        rng,
                    )
                else:
                    tensor, label, retained = cutmix(
                        tensor,
                        float(label),
                        partner_tensor,
                        float(partner_label),
                        float(config.get("cutmix_alpha", 1.0)),
                        rng,
                    )
                weight = np.float32(retained * weight + (1.0 - retained) * weights[partner_index])
        if include_weights:
            yield tensor, label, weight
        else:
            yield tensor


def _dataset(frame: pd.DataFrame, root: Path, config: dict[str, Any],
             training: bool, include_weights: bool) -> Any:
    tf = require_tensorflow()
    frequency_bins, time_frames = spectrogram_shape(config)
    shape = (frequency_bins, time_frames, 1)
    if include_weights:
        signature = (
            tf.TensorSpec(shape=shape, dtype=tf.float32),
            tf.TensorSpec(shape=(), dtype=tf.float32),
            tf.TensorSpec(shape=(), dtype=tf.float32),
        )
    else:
        signature = tf.TensorSpec(shape=shape, dtype=tf.float32)
    rng = np.random.default_rng(int(config["seed"]))
    dataset = tf.data.Dataset.from_generator(
        lambda: _example_iterator(
            frame, root, config, include_weights, training=training, rng=rng
        ),
        output_signature=signature,
    )
    if training:
        dataset = dataset.shuffle(min(len(frame), 4096), seed=int(config["seed"]), reshuffle_each_iteration=True)
    return dataset.batch(int(config.get("cnn_batch_size", 32))).prefetch(tf.data.AUTOTUNE)


def _estimate_frequency_statistics(
    frame: pd.DataFrame, root: Path, config: dict[str, Any]
) -> tuple[list[float], list[float], int]:
    """Fit normalization on training windows only to prevent validation leakage."""
    raw_config = dict(config, spectrogram_normalization="none")

    @lru_cache(maxsize=32)
    def loader(path: str) -> np.ndarray:
        return np.load(path, allow_pickle=False)

    total: np.ndarray | None = None
    squared: np.ndarray | None = None
    count = 0
    for row in frame.to_dict("records"):
        tensor = _window(row, root, raw_config, loader)[..., 0].astype(np.float64)
        if total is None:
            total = np.zeros(tensor.shape[0], dtype=np.float64)
            squared = np.zeros(tensor.shape[0], dtype=np.float64)
        if tensor.shape[0] != len(total):
            raise ValueError("Training spectrogram frequency dimensions are inconsistent")
        total += tensor.sum(axis=1)
        squared += np.square(tensor).sum(axis=1)
        count += tensor.shape[1]
    if total is None or squared is None or count == 0:
        raise ValueError("Cannot estimate spectrogram statistics from an empty training partition")
    mean = total / count
    variance = np.maximum(squared / count - np.square(mean), 1e-8)
    return mean.astype(float).tolist(), np.sqrt(variance).astype(float).tolist(), count


def prepare_spectrogram_config(
    training: pd.DataFrame, root: Path, config: dict[str, Any]
) -> dict[str, Any]:
    """Return an inference-complete config with train-only feature statistics."""
    prepared = dict(config)
    if prepared.get("spectrogram_normalization", "minmax") == "per_frequency":
        means = prepared.get("spectrogram_frequency_mean")
        stds = prepared.get("spectrogram_frequency_std")
        if not means or not stds:
            means, stds, frames = _estimate_frequency_statistics(training, root, prepared)
            prepared["spectrogram_frequency_mean"] = means
            prepared["spectrogram_frequency_std"] = stds
            prepared["spectrogram_statistics_training_frames"] = frames
    return prepared


def collapse_segment_scores(frame: pd.DataFrame, scores: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    """Average CNN window probabilities into one score per recording."""
    if len(frame) != len(scores):
        raise ValueError("Segment and score lengths differ")
    scored = frame[META_COLUMNS].copy()
    scored["score"] = np.asarray(scores, dtype=float)
    recordings = scored.groupby(META_COLUMNS, as_index=False).score.mean()
    values = recordings.pop("score").to_numpy()
    return recordings, values


def train_cnn(
    segments: pd.DataFrame,
    config: dict[str, Any],
    root: Path,
    synthetic: bool = False,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Train on windows, select participant threshold on validation, never read test scores."""
    tf = require_tensorflow()
    assert_no_leakage(segments)
    required = set(META_COLUMNS + ["processed_path", "start_sample", "valid_samples", "window_samples"])
    if missing := sorted(required - set(segments.columns)):
        raise ValueError(f"Missing CNN segment columns: {missing}")
    development = {name: segments[segments.split.eq(name)].reset_index(drop=True) for name in ("train", "validation")}
    if any(part.empty or part.label.nunique() != 2 for part in development.values()):
        raise ValueError("CNN training and validation splits must contain both classes")
    config = prepare_spectrogram_config(development["train"], root, config)
    tf.keras.utils.set_random_seed(int(config["seed"]))
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass
    probe = next(_example_iterator(development["train"].iloc[:1], root, config, False))
    model = build_cnn_model(tuple(probe.shape), config)
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=int(config.get("cnn_patience", 8)),
            restore_best_weights=True,
        )
    ]
    batch_size = int(config.get("cnn_batch_size", 32))
    history = model.fit(
        _dataset(development["train"], root, config, training=True, include_weights=True).repeat(),
        validation_data=_dataset(development["validation"], root, config, training=False, include_weights=True).repeat(),
        steps_per_epoch=math.ceil(len(development["train"]) / batch_size),
        validation_steps=math.ceil(len(development["validation"]) / batch_size),
        epochs=int(config.get("cnn_epochs", 50)),
        callbacks=callbacks,
        shuffle=False,
        verbose=int(config.get("cnn_verbose", 1)),
    )
    validation_segment_scores = model.predict(
        _dataset(development["validation"], root, config, training=False, include_weights=False),
        steps=math.ceil(len(development["validation"]) / batch_size),
        verbose=0,
    ).reshape(-1)
    validation_recordings, validation_scores = collapse_segment_scores(
        development["validation"], validation_segment_scores
    )
    threshold_selection = select_screening_threshold(
        validation_recordings,
        validation_scores,
        target_sensitivity=config.get("threshold_target_sensitivity", 0.90),
        min_specificity=config.get("threshold_min_specificity", 0.50),
    )
    threshold = threshold_selection["threshold"]
    validation_result, predictions = evaluate(validation_recordings, validation_scores, threshold)
    output = output_dir or root / "artifacts"
    for directory in ("models", "metrics", "figures"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    model_path = output / "models/heart_cnn.keras"
    model.save(model_path)
    model_kind = (
        "cnn_logmel"
        if config.get("spectrogram_type", "logmel") == "logmel"
        and config.get("cnn_architecture", "compact") == "compact"
        else "cnn_spectrogram"
    )
    metadata = {
        "schema_version": 1,
        "model_kind": model_kind,
        "target": "subject-level murmur Absent=0 vs Present=1; Unknown excluded",
        "config": config,
        "input_shape": list(probe.shape),
        "decision_threshold": threshold,
        "threshold_selection": threshold_selection,
    }
    (output / "models/heart_cnn.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    predictions.to_csv(output / "metrics/cnn_validation_predictions.csv", index=False)
    (output / "metrics/cnn_training_history.json").write_text(
        json.dumps(
            {name: [float(value) for value in values] for name, values in history.history.items()},
            indent=2,
        ),
        encoding="utf-8",
    )
    result = {
        "status": "synthetic_smoke_only" if synthetic else "real_data_development_evaluation",
        "target": metadata["target"],
        "sample_rate": config["sample_rate"],
        "signal_band_max_hz": config["signal_band_max_hz"],
        "seed": config["seed"],
        "python": platform.python_version(),
        "tensorflow": tf.__version__,
        "model_kind": model_kind,
        "spectrogram": {
            "type": config.get("spectrogram_type", "logmel"),
            "normalization": config.get("spectrogram_normalization", "minmax"),
            "input_shape": list(probe.shape),
            "training_only_augmentation": bool(config.get("augmentation_enabled", False)),
        },
        "development_split_counts": split_summary(segments[segments.split.isin(["train", "validation"])]),
        "threshold_selection": threshold_selection,
        "validation": validation_result,
        "training_epochs": len(history.history["loss"]),
        "best_validation_loss": float(min(history.history["val_loss"])),
        "development_segments_table_sha256": hashlib.sha256(
            segments[segments.split.isin(["train", "validation"])].to_csv(index=False).encode()
        ).hexdigest(),
        "holdout": {"evaluated": False, "status": config.get("holdout_status", "pending_new_data")},
        "warning": "Research screening only; no clinical validity established.",
    }
    (output / "metrics/cnn_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    plot_confusion(
        validation_result["subject"]["confusion_matrix"],
        output / "figures/cnn_validation_confusion_matrix.png",
        title="CNN validation participants: threshold-selected screening",
    )
    return result
