"""Lock and explicitly evaluate a final participant holdout exactly once."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .evaluation import evaluate, plot_confusion
from .splitting import assert_no_leakage


IDENTITY_COLUMNS = ["subject_group", "recording_id", "sha256"]


def _holdout_rows(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in [*IDENTITY_COLUMNS, "split"] if column not in frame]
    if missing:
        raise ValueError(f"Missing holdout identity columns: {missing}")
    rows = frame[frame.split.eq("test")][IDENTITY_COLUMNS].drop_duplicates().sort_values(IDENTITY_COLUMNS)
    if rows.empty:
        raise ValueError("No final holdout rows are assigned")
    if rows[IDENTITY_COLUMNS].isna().any().any() or rows.eq("").any().any():
        raise ValueError("Holdout identities and hashes must be complete before locking")
    return rows


def holdout_digest(frame: pd.DataFrame) -> str:
    """Hash only immutable identities and file hashes, never model outputs."""
    payload = _holdout_rows(frame).to_json(orient="records", force_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def lock_holdout(frame: pd.DataFrame, config: dict[str, Any], root: Path) -> dict[str, Any]:
    """Seal membership before final evaluation; refuse known/exposed partitions."""
    if config.get("holdout_status") != "locked_unseen":
        raise ValueError(
            "Refusing to label the historical split untouched. Add genuinely new external/device data, "
            "assign it once, then set holdout_status: locked_unseen before creating the lock."
        )
    assert_no_leakage(frame)
    rows = _holdout_rows(frame)
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": "test",
        "subject_count": int(rows.subject_group.nunique()),
        "recording_count": int(rows.recording_id.nunique()),
        "identity_sha256": holdout_digest(frame),
        "policy": "Do not inspect labels, scores or predictions until the model and threshold are frozen.",
    }
    path = root / "metadata/holdout_lock.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("identity_sha256") != payload["identity_sha256"]:
            raise ValueError("Holdout membership changed after it was locked")
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def verify_holdout_lock(frame: pd.DataFrame, config: dict[str, Any], root: Path) -> dict[str, Any]:
    """Require a sealed, unchanged and explicitly fresh final holdout."""
    if config.get("holdout_status") != "locked_unseen":
        raise ValueError("Final evaluation is disabled because this split is not marked locked_unseen")
    path = root / "metadata/holdout_lock.json"
    if not path.exists():
        raise ValueError("Missing metadata/holdout_lock.json; lock the fresh holdout before model development")
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("identity_sha256") != holdout_digest(frame):
        raise ValueError("Holdout membership or source hashes changed after locking")
    return lock


def evaluate_svm_holdout(features: pd.DataFrame, config: dict[str, Any], root: Path,
                         model_path: Path | None = None) -> dict[str, Any]:
    """Reveal one final SVM result only after model, threshold and holdout are locked."""
    assert_no_leakage(features)
    verify_holdout_lock(features, config, root)
    output_path = root / "artifacts/metrics/final_holdout_metrics.json"
    if output_path.exists():
        raise ValueError("Final holdout was already evaluated; refusing to overwrite or rerun it")
    model_path = model_path or root / "artifacts/models/heart_svm.joblib"
    bundle = joblib.load(model_path)
    if bundle.get("model_kind", "svm") != "svm" or "decision_threshold" not in bundle:
        raise ValueError("Model bundle is not a threshold-locked SVM")
    columns = bundle["feature_columns"]
    meta = ["subject_id", "subject_group", "recording_id", "dataset_source", "label", "split", "sha256"]
    recordings = features.groupby(meta)[columns].mean().reset_index()
    holdout = recordings[recordings.split.eq("test")]
    if holdout.empty or holdout.label.nunique() != 2:
        raise ValueError("Final holdout must contain both classes")
    scores = bundle["pipeline"].decision_function(holdout[columns])
    result, predictions = evaluate(holdout, scores, float(bundle["decision_threshold"]))
    result.update({
        "status": "final_locked_holdout_evaluation",
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "holdout_identity_sha256": holdout_digest(features),
        "warning": "One-time research evaluation; not evidence of clinical validity.",
    })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    predictions.to_csv(root / "artifacts/metrics/final_holdout_predictions.csv", index=False)
    plot_confusion(
        result["subject"]["confusion_matrix"],
        root / "artifacts/figures/final_holdout_confusion_matrix.png",
        title="Final locked holdout participants",
    )
    return result


def evaluate_cnn_holdout(segments: pd.DataFrame, config: dict[str, Any], root: Path,
                         model_path: Path | None = None) -> dict[str, Any]:
    """Reveal one final CNN result after the model, threshold and holdout are locked."""
    from .cnn import _dataset, collapse_segment_scores, require_tensorflow

    assert_no_leakage(segments)
    verify_holdout_lock(segments, config, root)
    output_path = root / "artifacts/metrics/final_holdout_metrics.json"
    if output_path.exists():
        raise ValueError("Final holdout was already evaluated; refusing to overwrite or rerun it")
    model_path = model_path or root / "artifacts/models/heart_cnn.keras"
    metadata_path = model_path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("model_kind") != "cnn_logmel" or "decision_threshold" not in metadata:
        raise ValueError("Model metadata is not a threshold-locked CNN")
    holdout_segments = segments[segments.split.eq("test")].reset_index(drop=True)
    if holdout_segments.empty or holdout_segments.label.nunique() != 2:
        raise ValueError("Final holdout must contain both classes")
    tf = require_tensorflow()
    model = tf.keras.models.load_model(model_path)
    segment_scores = model.predict(
        _dataset(holdout_segments, root, metadata["config"], training=False, include_weights=False),
        steps=math.ceil(len(holdout_segments) / int(metadata["config"].get("cnn_batch_size", 32))),
        verbose=0,
    ).reshape(-1)
    recordings, scores = collapse_segment_scores(holdout_segments, segment_scores)
    result, predictions = evaluate(recordings, scores, float(metadata["decision_threshold"]))
    result.update({
        "status": "final_locked_holdout_evaluation",
        "model_kind": "cnn_logmel",
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "holdout_identity_sha256": holdout_digest(segments),
        "warning": "One-time research evaluation; not evidence of clinical validity.",
    })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    predictions.to_csv(root / "artifacts/metrics/final_holdout_predictions.csv", index=False)
    plot_confusion(
        result["subject"]["confusion_matrix"],
        root / "artifacts/figures/final_holdout_confusion_matrix.png",
        title="Final locked holdout participants",
    )
    return result
