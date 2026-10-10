"""Explicitly authorized Lung training; importing/preflight never fits a model."""
import json
from pathlib import Path
import time
from typing import Any
import numpy as np
import pandas as pd
from .acquisition_lung import digest
from .lung_preprocessing import validate_config
from .lung_training_policy import load_policy, development_callbacks, final_learning_rates, learning_rate_logger, model_dropout
from .lung_training_log import TrainingLog, runtime_details, process_callback


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


INPUT_PIPELINE_VERSION = "lung-cache-dataset-v2"


def build_dataset(cache: str | Path, rows: pd.DataFrame, mean: np.ndarray,
                  std: np.ndarray, *, batch_size: int, training: bool,
                  seed: int) -> Any:
    """Stream aligned cache blocks with known batch count and TRAIN-only shuffling.

    Shuffle filenames before loading tensors so a full permutation costs only
    filename storage. Each iteration visits every supplied row exactly once,
    including the final short batch; evaluation order remains fixed.
    """
    if rows.empty or type(batch_size) is not int or batch_size <= 0:
        raise ValueError("Nonempty Lung rows and a positive integer batch size required")
    if "split" in rows and not set(rows.split).issubset({"train", "validation"}):
        raise ValueError("Official test/quarantine cannot enter a development dataset")
    cache = Path(cache).resolve()
    names = rows.file.astype(str).tolist()
    for name in names:
        path = (cache / name).resolve()
        if path.parent != cache or path.suffix != ".npz":
            raise ValueError("Unsafe Lung cache path")
    features, truth, _ = load_block(cache / names[0])
    mean, std = np.asarray(mean, np.float32), np.asarray(std, np.float32)
    if (mean.shape != (features.shape[1],) or std.shape != mean.shape
            or not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std <= 0)):
        raise ValueError("Invalid Lung dataset normalization")
    feature_shape, target_shape = features.shape, truth.shape
    import tensorflow as tf
    dataset = tf.data.Dataset.from_tensor_slices(names)
    if training:
        dataset = dataset.shuffle(len(names), seed=seed, reshuffle_each_iteration=True)

    def load(name):
        x, y, mask = load_block(cache / name.decode("utf-8"))
        if x.shape != feature_shape or y.shape != target_shape:
            raise ValueError("Inconsistent Lung cache geometry")
        return np.clip((x - mean) / std, -5, 5), np.concatenate([y, mask], axis=-1)

    def map_block(name):
        x, packed = tf.numpy_function(load, [name], [tf.float32, tf.float32])
        x.set_shape(feature_shape)
        packed.set_shape((*target_shape[:-1], target_shape[-1] * 2))
        return x, packed

    dataset = dataset.map(map_block, num_parallel_calls=1, deterministic=True)
    dataset = dataset.batch(batch_size, drop_remainder=False)
    batches = (len(names) + batch_size - 1) // batch_size
    dataset = dataset.apply(tf.data.experimental.assert_cardinality(batches))
    return dataset.prefetch(1)


def statistics(cache, index, *, log=None):
    total = squares = None
    count = 0
    positives = negatives = None
    for position, name in enumerate(index.file, 1):
        x, y, mask = load_block(Path(cache) / name)
        selected = x[np.any(mask > 0, axis=1)].astype(np.float64)
        if total is None:
            total = np.zeros(x.shape[1]); squares = total.copy()
            positives = np.zeros(y.shape[1]); negatives = positives.copy()
        total += selected.sum(axis=0); squares += (selected ** 2).sum(axis=0); count += len(selected)
        positives += (y * mask).sum(axis=0); negatives += ((1 - y) * mask).sum(axis=0)
        if log is not None:
            log.progress("training_statistics", position, len(index))
    if not count or np.any(positives == 0) or np.any(negatives == 0):
        raise ValueError("TRAIN needs valid positive/negative support for every selected class")
    mean = total / count
    std = np.maximum(np.sqrt(np.maximum(squares / count - mean ** 2, 0)), 1e-5)
    return mean.astype(np.float32), std.astype(np.float32), np.clip(negatives / positives, .25, 20).astype(np.float32)


def train(cache, audit_path, output, *, authorized=False, folds=0, training_policy=None, progress_interval=30):
    """Only this function fits weights; explicit authorization is mandatory."""
    if authorized is not True:
        raise PermissionError("Training requires the user's go-ahead and --authorized-training")
    log = TrainingLog(progress_interval)
    log.event("preflight_started", cache=str(cache), audit=str(audit_path))
    config, index = preflight(cache, audit_path)
    policy = load_policy(training_policy, config)
    log.event("preflight_completed", windows=len(index), classes=config["classes"])
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
    log.bind(output)
    (output / "status.json").write_text(json.dumps({"status": "running", "started": time.time()}))
    (output / "source.json").write_text(json.dumps({"index_sha256": digest(Path(cache) / "index.csv"),
        "audit_sha256": digest(audit_path), "config": config, "evaluation_role": "development_only",
        "training_policy": policy, "training_policy_sha256": digest(training_policy) if training_policy is not None else None,
        "input_pipeline_version": INPUT_PIPELINE_VERSION,
        "shuffle_policy": "seeded_full_filename_permutation_each_training_epoch"}, indent=2))
    partitions = [(index[index.split == "train"], index[index.split == "validation"])]
    if folds:
        if folds < 2 or index.group.nunique() < folds:
            raise ValueError("Insufficient distinct groups for CV")
        partitions = [(index.iloc[a], index.iloc[b]) for a, b in GroupKFold(folds).split(index, groups=index.group)]
    predictions = []
    try:
        log.event("runtime", **runtime_details(tf))
        log.event("experiment_started", output=str(output), policy=policy, initial_lr=config["learning_rate"],
                  dropout=model_dropout(policy),
                  maximum_epochs=config["epochs"], patience=config["patience"], batch_size=config["batch_size"],
                  folds=len(partitions), input_pipeline=INPUT_PIPELINE_VERSION, official_test="sealed")
        for fold, (fitting, validation) in enumerate(partitions):
            log.event("fold_started", fold=fold, seed=config["seed"] + fold, training_windows=len(fitting),
                      validation_windows=len(validation), training_groups=fitting.group.nunique(),
                      validation_groups=validation.group.nunique())
            tf.keras.utils.set_random_seed(config["seed"] + fold)
            mean, std, weights = statistics(cache, fitting, log=log)
            log.event("statistics_completed", positive_weights=dict(zip(config["classes"], weights.tolist())))
            x, _, _ = load_block(Path(cache) / fitting.iloc[0].file)
            model = build_model(x.shape, config["classes"], positive_weights=weights,
                                learning_rate=config["learning_rate"], dropout=model_dropout(policy))
            log.event("model_built", input_shape=list(x.shape), dropout=model_dropout(policy))
            folder = output / f"fold-{fold}"
            folder.mkdir()
            np.savez(folder / "normalization.npz", mean=mean, std=std)
            training_data = build_dataset(cache, fitting, mean, std, batch_size=config["batch_size"],
                                          training=True, seed=config["seed"] + fold)
            validation_data = build_dataset(cache, validation, mean, std, batch_size=config["batch_size"],
                                            training=False, seed=config["seed"] + fold)
            callbacks = development_callbacks(folder, config, policy)
            stopper = next(c for c in callbacks if isinstance(c, tf.keras.callbacks.EarlyStopping))
            callbacks.append(process_callback(log, epochs=config["epochs"],
                steps=(len(fitting) + config["batch_size"] - 1) // config["batch_size"], early_stopper=stopper,
                checkpoint=folder / "best.weights.h5"))
            log.event("fitting_started", fold=fold, validation_batches=(len(validation) + config["batch_size"] - 1) // config["batch_size"])
            history = model.fit(training_data, validation_data=validation_data, epochs=config["epochs"], shuffle=False,
                callbacks=callbacks, verbose=2)
            model.save(folder / "model.keras")
            log.event("model_saved", path=str(folder / "model.keras"))
            scores, truths, masks = [], [], []
            log.event("development_prediction_started", fold=fold, windows=len(validation))
            for position, row in enumerate(validation.itertuples(), 1):
                features, truth, validity = load_block(Path(cache) / row.file)
                probability = np.asarray(model(np.clip((features - mean) / std, -5, 5)[None], training=False))[0]
                scores.append(probability); truths.append(truth); masks.append(validity)
                predictions.append({"fold": fold, "group": row.group, "file": row.file})
                log.progress("development_prediction", position, len(validation))
            truth, probability, validity = np.concatenate(truths), np.concatenate(scores), np.concatenate(masks)
            log.event("threshold_selection_started", fold=fold, population="development_only")
            thresholds = select_thresholds(truth, probability, validity)
            log.event("threshold_selection_completed", thresholds=dict(zip(config["classes"], thresholds)))
            log.event("evaluation_started", fold=fold)
            metrics = frame_metrics(truth, probability, validity, thresholds)
            np.savez_compressed(folder / "development_predictions.npz", truth=truth, scores=probability, mask=validity)
            (folder / "evaluation.json").write_text(json.dumps({"role": "development_only", "classes": config["classes"],
                "thresholds": thresholds, "metrics": metrics,
                "groups": sorted(validation.group.unique()), "patient_disjoint_verified": False}, indent=2))
            (folder / "history.json").write_text(json.dumps(history.history))
            for name, metric in zip(config["classes"], metrics):
                log.event("class_evaluation", class_name=name, **metric)
            log.event("fold_completed", fold=fold, artifacts=str(folder))
            tf.keras.backend.clear_session()
        (output / "prediction_index.json").write_text(json.dumps(predictions, indent=2))
        (output / "status.json").write_text(json.dumps({"status": "completed", "finished": time.time(), "deployment_eligible": False}))
        log.event("experiment_completed", output=str(output), deployment_eligible=False)
    except Exception as error:
        (output / "status.json").write_text(json.dumps({"status": "failed", "finished": time.time()}))
        log.event("experiment_failed", error_type=type(error).__name__, error=str(error))
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


def train_final(cache, audit_path, selection_path, output, *, authorized=False, progress_interval=30):
    """Fit all development groups with a frozen, development-selected epoch count."""
    if authorized is not True:
        raise PermissionError("Final training requires the user's explicit go-ahead")
    log = TrainingLog(progress_interval)
    log.event("final_preflight_started", cache=str(cache), selection=str(selection_path))
    config, index = preflight(cache, audit_path)
    selection = json.loads(Path(selection_path).read_text())
    from .lung_temporal import LOCALIZATION_VERSION
    if selection.get("localization_version", "lung-frame-events-v1") not in {"lung-frame-events-v1", LOCALIZATION_VERSION}:
        raise ValueError("Unsupported frozen localization version")
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
    policy, rates = final_learning_rates(selection, config)
    output = Path(output)
    if output.exists():
        raise ValueError("Never overwrite a final experiment")
    import tensorflow as tf
    from .lung_models import build_model
    output.mkdir(parents=True)
    log.bind(output)
    (output / "status.json").write_text(json.dumps({"status": "running", "model_role": "final_deployment_candidate"}))
    try:
        log.event("runtime", **runtime_details(tf))
        log.event("final_preflight_completed", windows=len(index), groups=index.group.nunique(),
                  classes=config["classes"], fixed_epochs=selection["epochs"], policy=policy,
                  dropout=model_dropout(policy),
                  official_test="sealed", validation_callbacks=False)
        mean, std, weights = statistics(cache, index, log=log)
        log.event("statistics_completed", positive_weights=dict(zip(config["classes"], weights.tolist())))
        x, _, _ = load_block(Path(cache) / index.iloc[0].file)
        tf.keras.utils.set_random_seed(config["seed"])
        model = build_model(x.shape, config["classes"], positive_weights=weights,
                            learning_rate=config["learning_rate"], dropout=model_dropout(policy))
        dataset = build_dataset(cache, index, mean, std, batch_size=config["batch_size"],
                                training=True, seed=config["seed"])
        callbacks = []
        if rates is not None:
            callbacks.append(tf.keras.callbacks.LearningRateScheduler(lambda epoch, current: rates[epoch], verbose=1))
        callbacks.extend([learning_rate_logger(), tf.keras.callbacks.CSVLogger(str(output / "history.csv"))])
        callbacks.append(process_callback(log, epochs=selection["epochs"],
            steps=(len(index) + config["batch_size"] - 1) // config["batch_size"]))
        log.event("final_fitting_started", output=str(output), input_shape=list(x.shape))
        model.fit(dataset, epochs=selection["epochs"], shuffle=False,
                  callbacks=callbacks, verbose=2)
        model.save(output / "model.keras")
        log.event("model_saved", path=str(output / "model.keras"))
        np.savez(output / "normalization.npz", mean=mean, std=std)
        (output / "config.json").write_text(json.dumps(config, indent=2))
        (output / "selection.json").write_text(json.dumps(selection, indent=2))
        (output / "source.json").write_text(json.dumps({"audit_sha256": digest(audit_path),
            "index_sha256": digest(Path(cache) / "index.csv"), "selection_sha256": digest(output / "selection.json"),
            "model_role": "final_deployment_candidate", "model_sha256": digest(output / "model.keras"),
            "training_policy": policy, "learning_rates": rates,
            "config_sha256": digest(output / "config.json"), "normalization_sha256": digest(output / "normalization.npz"),
            "input_pipeline_version": INPUT_PIPELINE_VERSION,
            "shuffle_policy": "seeded_full_filename_permutation_each_training_epoch"}, indent=2))
        (output / "status.json").write_text(json.dumps({"status": "completed", "deployment_eligible": False}))
        log.event("experiment_completed", output=str(output), deployment_eligible=False)
    except Exception as error:
        (output / "status.json").write_text(json.dumps({"status": "failed", "deployment_eligible": False}))
        log.event("experiment_failed", error_type=type(error).__name__, error=str(error))
        raise
