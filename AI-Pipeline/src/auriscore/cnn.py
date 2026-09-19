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

from .evaluation import evaluate, plot_confusion, select_screening_threshold
from .features import extract_logmel_tensor
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
    """Build a compact 2D CNN suitable for later TensorFlow Lite conversion."""
    tf = require_tensorflow()
    inputs = tf.keras.Input(shape=input_shape, name="logmel")
    x = inputs
    for filters in (16, 32, 64):
        x = tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False)(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.Activation("relu")(x)
        x = tf.keras.layers.MaxPooling2D(pool_size=(2, 2))(x)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(float(config.get("cnn_dropout", 0.30)))(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="murmur_probability")(x)
    model = tf.keras.Model(inputs, outputs, name="auriscore_heart_cnn")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(float(config.get("cnn_learning_rate", 1e-3))),
        loss=tf.keras.losses.BinaryCrossentropy(),
        metrics=[
            tf.keras.metrics.Recall(name="sensitivity"),
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.AUC(name="roc_auc"),
            tf.keras.metrics.AUC(name="pr_auc", curve="PR"),
        ],
    )
    return model


def _window(row: dict[str, Any], root: Path, config: dict[str, Any], loader: Any) -> np.ndarray:
    audio = loader(str(root / row["processed_path"]))
    start = int(row["start_sample"])
    valid = int(row["valid_samples"])
    size = int(row["window_samples"])
    signal = np.pad(audio[start:start + valid], (0, size - valid))
    return extract_logmel_tensor(signal, config)[..., np.newaxis]


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


def _example_iterator(frame: pd.DataFrame, root: Path, config: dict[str, Any],
                      include_weights: bool) -> Iterator[Any]:
    @lru_cache(maxsize=32)
    def loader(path: str) -> np.ndarray:
        return np.load(path, allow_pickle=False)

    weights = _participant_weights(frame) if include_weights else np.ones(len(frame), dtype=np.float32)
    for row, weight in zip(frame.to_dict("records"), weights, strict=True):
        tensor = _window(row, root, config, loader)
        label = np.float32(row["label"] == "Present")
        if include_weights:
            yield tensor, label, weight
        else:
            yield tensor


def _dataset(frame: pd.DataFrame, root: Path, config: dict[str, Any],
             training: bool, include_weights: bool) -> Any:
    tf = require_tensorflow()
    shape = (int(config["n_mels"]), None, 1)
    if include_weights:
        signature = (
            tf.TensorSpec(shape=shape, dtype=tf.float32),
            tf.TensorSpec(shape=(), dtype=tf.float32),
            tf.TensorSpec(shape=(), dtype=tf.float32),
        )
    else:
        signature = tf.TensorSpec(shape=shape, dtype=tf.float32)
    dataset = tf.data.Dataset.from_generator(
        lambda: _example_iterator(frame, root, config, include_weights),
        output_signature=signature,
    )
    if training:
        dataset = dataset.shuffle(min(len(frame), 4096), seed=int(config["seed"]), reshuffle_each_iteration=True)
    return dataset.batch(int(config.get("cnn_batch_size", 32))).prefetch(tf.data.AUTOTUNE)


def collapse_segment_scores(frame: pd.DataFrame, scores: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    """Average CNN window probabilities into one score per recording."""
    if len(frame) != len(scores):
        raise ValueError("Segment and score lengths differ")
    scored = frame[META_COLUMNS].copy()
    scored["score"] = np.asarray(scores, dtype=float)
    recordings = scored.groupby(META_COLUMNS, as_index=False).score.mean()
    values = recordings.pop("score").to_numpy()
    return recordings, values


def train_cnn(segments: pd.DataFrame, config: dict[str, Any], root: Path,
              synthetic: bool = False) -> dict[str, Any]:
    """Train on windows, select participant threshold on validation, never read test scores."""
    tf = require_tensorflow()
    assert_no_leakage(segments)
    required = set(META_COLUMNS + ["processed_path", "start_sample", "valid_samples", "window_samples"])
    if missing := sorted(required - set(segments.columns)):
        raise ValueError(f"Missing CNN segment columns: {missing}")
    development = {name: segments[segments.split.eq(name)].reset_index(drop=True) for name in ("train", "validation")}
    if any(part.empty or part.label.nunique() != 2 for part in development.values()):
        raise ValueError("CNN training and validation splits must contain both classes")
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
    output = root / "artifacts"
    for directory in ("models", "metrics", "figures"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    model_path = output / "models/heart_cnn.keras"
    model.save(model_path)
    metadata = {
        "schema_version": 1,
        "model_kind": "cnn_logmel",
        "target": "subject-level murmur Absent=0 vs Present=1; Unknown excluded",
        "config": config,
        "input_shape": list(probe.shape),
        "decision_threshold": threshold,
        "threshold_selection": threshold_selection,
    }
    (output / "models/heart_cnn.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    predictions.to_csv(output / "metrics/cnn_validation_predictions.csv", index=False)
    result = {
        "status": "synthetic_smoke_only" if synthetic else "real_data_development_evaluation",
        "target": metadata["target"],
        "sample_rate": config["sample_rate"],
        "signal_band_max_hz": config["signal_band_max_hz"],
        "seed": config["seed"],
        "python": platform.python_version(),
        "tensorflow": tf.__version__,
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
