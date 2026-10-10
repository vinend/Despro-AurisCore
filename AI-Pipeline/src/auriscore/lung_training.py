"""Explicitly authorized Lung training; importing/preflight never fits a model."""
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from .acquisition_lung import digest
from .lung_preprocessing import validate_config


def preflight(cache, audit_path):
    cache = Path(cache)
    config = json.loads((cache / "config.json").read_text())
    validate_config(config)
    audit = json.loads(Path(audit_path).read_text())
    provenance = json.loads((cache / "provenance.json").read_text())
    if (provenance.get("audit_sha256") != digest(audit_path)
            or provenance.get("config_sha256") != digest(cache / "config.json")
            or provenance.get("index_sha256") != digest(cache / "index.csv")
            or provenance.get("recordings_sha256") != digest(Path(audit_path).parent / "recordings.csv")
            or provenance.get("events_sha256") != digest(Path(audit_path).parent / "events.csv")):
        raise ValueError("Stale Lung cache provenance")
    if (audit.get("test_inventory_present") is not True or audit.get("near_duplicate_review_complete") is not True
            or audit.get("annotation_coverage_verified") is not True or config.get("annotation_coverage_verified") is not True):
        raise ValueError("Official test inventory, near-duplicate review and annotation coverage must be audited before training")
    if not set(config["classes"]).issubset(audit.get("observed_train_labels", [])):
        raise ValueError("Training classes lack verified source annotations")
    index = pd.read_csv(cache / "index.csv", dtype={"group": str})
    if not set(index.split).issubset({"train", "validation"}) or not {"train", "validation"}.issubset(index.split):
        raise ValueError("Development cache must exclude test/quarantine and include train/validation")
    if (index.groupby("group").split.nunique() > 1).any() or (index.groupby("source_sha256").split.nunique() > 1).any():
        raise ValueError("Development group/content leakage")
    # Paths from a cache index must remain inside the cache directory.
    for name in index.file:
        path = (cache / name).resolve()
        if path.parent != cache.resolve() or path.suffix != ".npz" or not path.is_file():
            raise ValueError("Unsafe/missing cache file")
    return config, index


def load_block(path):
    with np.load(path, allow_pickle=False) as data:
        x, y, mask = (data[k].copy().astype(np.float32) for k in ("features", "targets", "mask"))
    if (x.ndim != 2 or y.ndim != 2 or y.shape != mask.shape or len(y) != len(x)
            or not all(np.isfinite(a).all() for a in (x, y, mask)) or not np.isin(y, [0, 1]).all()
            or not np.isin(mask, [0, 1]).all()):
        raise ValueError("Malformed Lung cache")
    return x, y, mask


def statistics(cache, index):
    total = squares = None
    count = 0
    positives = negatives = None
    for name in index.file:
        x, y, mask = load_block(Path(cache) / name)
        selected = x[np.any(mask > 0, axis=1)].astype(np.float64)
        if total is None:
            total = np.zeros(x.shape[1]); squares = total.copy()
            positives = np.zeros(y.shape[1]); negatives = positives.copy()
        total += selected.sum(axis=0); squares += (selected ** 2).sum(axis=0); count += len(selected)
        positives += (y * mask).sum(axis=0); negatives += ((1 - y) * mask).sum(axis=0)
    if not count or np.any(positives == 0) or np.any(negatives == 0):
        raise ValueError("TRAIN needs valid positive/negative support for every selected class")
    mean = total / count
    std = np.maximum(np.sqrt(np.maximum(squares / count - mean ** 2, 0)), 1e-5)
    return mean.astype(np.float32), std.astype(np.float32), np.clip(negatives / positives, .25, 20).astype(np.float32)


def train(cache, audit_path, output, *, authorized=False, folds=0):
    """Only this function fits weights; explicit authorization is mandatory."""
    if authorized is not True:
        raise PermissionError("Training requires the user's go-ahead and --authorized-training")
    config, index = preflight(cache, audit_path)
    if folds and (folds < 2 or index.group.nunique() < folds):
        raise ValueError("Insufficient distinct groups for CV")
    import tensorflow as tf
    from sklearn.model_selection import GroupKFold
    from .lung_models import build_model
    from .lung_evaluation import select_thresholds, frame_metrics
    output = Path(output)
    if output.exists():
        raise ValueError("Experiment directory already exists; never overwrite experiments")
    output.mkdir(parents=True)
    (output / "status.json").write_text(json.dumps({"status": "running", "started": time.time()}))
    (output / "source.json").write_text(json.dumps({"index_sha256": digest(Path(cache) / "index.csv"),
        "audit_sha256": digest(audit_path), "config": config, "evaluation_role": "development_only"}, indent=2))
    partitions = [(index[index.split == "train"], index[index.split == "validation"])]
    if folds:
        if folds < 2 or index.group.nunique() < folds:
            raise ValueError("Insufficient distinct groups for CV")
        partitions = [(index.iloc[a], index.iloc[b]) for a, b in GroupKFold(folds).split(index, groups=index.group)]
    predictions = []
    try:
        for fold, (fitting, validation) in enumerate(partitions):
            tf.keras.utils.set_random_seed(config["seed"] + fold)
            mean, std, weights = statistics(cache, fitting)
            x, y, mask = load_block(Path(cache) / fitting.iloc[0].file)
            model = build_model(x.shape, config["classes"], positive_weights=weights, learning_rate=config["learning_rate"])
            folder = output / f"fold-{fold}"
            folder.mkdir()
            np.savez(folder / "normalization.npz", mean=mean, std=std)
            def dataset(rows):
                def generate():
                    for name in rows.file:
                        features, truth, validity = load_block(Path(cache) / name)
                        yield np.clip((features - mean) / std, -5, 5), np.concatenate([truth, validity], axis=-1)
                result = tf.data.Dataset.from_generator(generate, output_signature=(
                    tf.TensorSpec(x.shape, tf.float32), tf.TensorSpec((*y.shape[:-1], y.shape[-1] * 2), tf.float32)))
                return result.batch(config["batch_size"]).prefetch(1)
            history = model.fit(dataset(fitting), validation_data=dataset(validation), epochs=config["epochs"],
                callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=config["patience"], restore_best_weights=True),
                           tf.keras.callbacks.CSVLogger(str(folder / "history.csv")),
                           tf.keras.callbacks.ModelCheckpoint(str(folder / "best.weights.h5"), save_weights_only=True, save_best_only=True)], verbose=2)
            model.save(folder / "model.keras")
            scores, truths, masks = [], [], []
            for row in validation.itertuples():
                features, truth, validity = load_block(Path(cache) / row.file)
                probability = np.asarray(model(np.clip((features - mean) / std, -5, 5)[None], training=False))[0]
                scores.append(probability); truths.append(truth); masks.append(validity)
                predictions.append({"fold": fold, "group": row.group, "file": row.file})
            truth, probability, validity = np.concatenate(truths), np.concatenate(scores), np.concatenate(masks)
            thresholds = select_thresholds(truth, probability, validity)
            np.savez_compressed(folder / "development_predictions.npz", truth=truth, scores=probability, mask=validity)
            (folder / "evaluation.json").write_text(json.dumps({"role": "development_only", "classes": config["classes"],
                "thresholds": thresholds, "metrics": frame_metrics(truth, probability, validity, thresholds),
                "groups": sorted(validation.group.unique()), "patient_disjoint_verified": False}, indent=2))
            (folder / "history.json").write_text(json.dumps(history.history))
            tf.keras.backend.clear_session()
        (output / "prediction_index.json").write_text(json.dumps(predictions, indent=2))
        (output / "status.json").write_text(json.dumps({"status": "completed", "finished": time.time(), "deployment_eligible": False}))
    except Exception:
        (output / "status.json").write_text(json.dumps({"status": "failed", "finished": time.time()}))
        raise


def export_tflite(model_path, destination, *, representative=None):
    """Explicit export; optional INT8 calibration uses supplied TRAIN tensors only."""
    import tensorflow as tf
    model = tf.keras.models.load_model(model_path, compile=False)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    if representative is not None:
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = representative
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.int8; converter.inference_output_type = tf.int8
    Path(destination).write_bytes(converter.convert())


def train_final(cache, audit_path, selection_path, output, *, authorized=False):
    """Fit all development groups with a frozen, development-selected epoch count."""
    if authorized is not True:
        raise PermissionError("Final training requires the user's explicit go-ahead")
    config, index = preflight(cache, audit_path)
    selection = json.loads(Path(selection_path).read_text())
    if (selection.get("role") not in {"development_validation", "train_only_oof"}
            or selection.get("config") != config
            or selection.get("index_sha256") != digest(Path(cache) / "index.csv")
            or type(selection.get("epochs")) is not int or not 1 <= selection["epochs"] <= config["epochs"]
            or len(selection.get("thresholds", [])) != len(config["classes"])
            or not np.isfinite(selection["thresholds"]).all()
            or np.any((np.asarray(selection["thresholds"]) < 0) | (np.asarray(selection["thresholds"]) > 1))
            or set(selection.get("postprocessing", {})) != {"minimum_s", "merge_gap_s"}
            or any(not isinstance(v, (int, float)) or not np.isfinite(v) or not 0 <= v <= 2
                   for v in selection["postprocessing"].values())):
        raise ValueError("A frozen development selection bound to this cache/config is required")
    output = Path(output)
    if output.exists():
        raise ValueError("Never overwrite a final experiment")
    import tensorflow as tf
    from .lung_models import build_model
    mean, std, weights = statistics(cache, index)
    x, y, _ = load_block(Path(cache) / index.iloc[0].file)
    tf.keras.utils.set_random_seed(config["seed"])
    model = build_model(x.shape, config["classes"], positive_weights=weights, learning_rate=config["learning_rate"])
    def generate():
        for name in index.file:
            features, truth, mask = load_block(Path(cache) / name)
            yield np.clip((features - mean) / std, -5, 5), np.concatenate([truth, mask], axis=-1)
    dataset = tf.data.Dataset.from_generator(generate, output_signature=(tf.TensorSpec(x.shape, tf.float32),
        tf.TensorSpec((*y.shape[:-1], y.shape[-1] * 2), tf.float32))).batch(config["batch_size"]).prefetch(1)
    output.mkdir(parents=True)
    (output / "status.json").write_text(json.dumps({"status": "running", "model_role": "final_deployment_candidate"}))
    try:
        model.fit(dataset, epochs=selection["epochs"], callbacks=[tf.keras.callbacks.CSVLogger(str(output / "history.csv"))], verbose=2)
        model.save(output / "model.keras")
        np.savez(output / "normalization.npz", mean=mean, std=std)
        (output / "config.json").write_text(json.dumps(config, indent=2))
        (output / "selection.json").write_text(json.dumps(selection, indent=2))
        (output / "source.json").write_text(json.dumps({"audit_sha256": digest(audit_path),
            "index_sha256": digest(Path(cache) / "index.csv"), "selection_sha256": digest(output / "selection.json"),
            "model_role": "final_deployment_candidate", "model_sha256": digest(output / "model.keras"),
            "config_sha256": digest(output / "config.json"), "normalization_sha256": digest(output / "normalization.npz")}, indent=2))
        (output / "status.json").write_text(json.dumps({"status": "completed", "deployment_eligible": False}))
    except Exception:
        (output / "status.json").write_text(json.dumps({"status": "failed", "deployment_eligible": False}))
        raise
