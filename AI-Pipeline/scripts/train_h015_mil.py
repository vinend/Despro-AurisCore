"""Locked, detached H015 train-only CV and gated one-time validation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split

import _bootstrap  # noqa: F401
from auriscore.cnn import _estimate_frequency_statistics
from auriscore.evaluation import metrics, select_screening_threshold
from auriscore.mil import BagTensorLoader, ParticipantBag, SiteAwareMIL, build_bags, read_one_split

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "analysis/EXP-H015-heart-site-aware-mil"
R = ROOT / "results/EXP-H015-heart-site-aware-mil"
H014 = ROOT / "results/EXP-H014-cnn-per-frequency-augmentation-declared-positive-only"
NAME = "EXP-H015-heart-site-aware-mil"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def status(state: str, **extra: Any) -> None:
    write_json(R / "status.json", {
        "experiment": NAME, "status": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid() if state == "running" else None, **extra,
    })


def gpu_check() -> str:
    if tf.__version__ != "2.20.0":
        raise RuntimeError(f"TensorFlow changed: {tf.__version__}")
    devices = tf.config.list_physical_devices("GPU")
    if len(devices) != 1:
        raise RuntimeError(f"Expected /GPU:0, found {devices}")
    name = tf.config.experimental.get_device_details(devices[0]).get("device_name", "")
    if "RTX 4060" not in name:
        raise RuntimeError(f"Unexpected GPU: {name}")
    print(f"TensorFlow {tf.__version__}; /GPU:0 {name}", flush=True)
    return name


def train_frame() -> pd.DataFrame:
    frame = read_one_split(ROOT / "data/processed/segments.csv", "train")
    labels = frame[["subject_group", "label"]].drop_duplicates()
    if (labels.subject_group.nunique(), frame.recording_id.nunique(), len(frame)) != (568, 2070, 15954):
        raise RuntimeError("Train inventory changed")
    if labels.label.value_counts().to_dict() != {"Absent": 458, "Present": 110}:
        raise RuntimeError("Train label inventory changed")
    return frame


def assignments_for(frame: pd.DataFrame) -> pd.DataFrame:
    labels = frame[["subject_group", "label"]].drop_duplicates().sort_values("subject_group")
    ids = labels.subject_group.astype(str).to_numpy()
    y = (labels.label == "Present").to_numpy().astype(int)
    rows = []
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    for fold, (outer_train, outer_eval) in enumerate(splitter.split(ids, y), 1):
        fit, early = train_test_split(outer_train, test_size=.20, stratify=y[outer_train],
                                      random_state=42 + fold)
        for role, members in (("fit", fit), ("early_stop", early), ("outer_eval", outer_eval)):
            rows += [{"participant_id": ids[i], "label": labels.label.iloc[i],
                      "fold": fold, "role": role} for i in members]
    result = pd.DataFrame(rows).sort_values(["fold", "participant_id"]).reset_index(drop=True)
    if len(result) != 568 * 5 or (result.groupby(["fold", "participant_id"]).size() != 1).any():
        raise RuntimeError("Fold assignment has leakage or missing participants")
    return result


def memory_smoke() -> None:
    """A synthetic participant batch-4 backward pass before protocol lock."""
    tf.keras.utils.set_random_seed(42)
    model = SiteAwareMIL()
    optimizer = tf.keras.optimizers.Adam(.001)
    total = None
    for segments, recordings in ((16, 2), (24, 3), (40, 4), (102, 9)):
        x = tf.zeros((segments, 40, 313, 1))
        rec = tf.constant(np.arange(segments) % recordings, tf.int32)
        sites = tf.constant(np.arange(recordings) % 5, tf.int32)
        with tf.GradientTape() as tape:
            score = model((x, rec, sites), training=True)
            loss = tf.keras.losses.binary_crossentropy(
                tf.constant([1.]), tf.reshape(score, [1])) / 4.
        gradients = [tf.convert_to_tensor(g) for g in
                     tape.gradient(loss, model.trainable_variables)]
        total = [g if old is None else old + g for old, g in
                 zip(total or [None] * len(gradients), gradients)]
    optimizer.apply_gradients(zip(total, model.trainable_variables))
    tf.keras.backend.clear_session()
    print("Synthetic participant batch-4 forward/backward memory smoke PASS", flush=True)


def protocol(preflight: dict[str, Any], folds_hash: str, gpu: str) -> dict[str, Any]:
    return {
        "version": 1, "experiment": NAME, "master_seed": 42,
        "participant_split_source": "data/processed/segments.csv; train split parsed alone until gate",
        "train_participants": 568, "train_present": 110, "train_absent": 458,
        "train_recordings": 2070, "train_segments": 15954,
        "outside_declared_present_recordings_retained": 85,
        "fold_assignments_sha256": folds_hash,
        "train_participant_label_sha256": preflight["train_participant_label_sha256"],
        "reference_development_split_sha256": preflight["reference_development_split_sha256"],
        "h014_config_sha256": preflight["h014_config_sha256"],
        "h014_model_sha256": preflight["h014_model_sha256"],
        "encoder_initialization": "from_scratch", "h014_weights_reused": False,
        "encoder": "H014 compact CNN topology Conv16/32/64 + BN/ReLU/MaxPool, GAP, Dropout(0.30), 64D preclassifier",
        "segment_input_shape": [40, 313, 1],
        "segment_to_recording": "arithmetic_mean_of_segment_embeddings",
        "site_vocabulary": ["AV", "MV", "PV", "TV", "Phc", "UNKNOWN"],
        "site_embedding_dim": 8, "attention_input_dim": 72,
        "attention": "single-head Dense(32,relu), Dropout(.30), Dense(1,linear), masked softmax",
        "attention_hidden_dim": 32, "attention_value": "acoustic_recording_embedding_64D_only",
        "participant_classifier": "Dense(32,relu), Dropout(.30), Dense(1,sigmoid)",
        "classifier_hidden_dim": 32, "dropout": .30,
        "participant_supervision": True, "recording_supervision": False,
        "bag_policy": "all eligible recordings; no declared-site filter or recording labels",
        "loss": "participant_binary_crossentropy",
        "class_weight_policy": "gradient-update participants N/(2*N_c)",
        "participant_batch_size": 4,
        "batch_implementation": "4 sequential participant microbatches, accumulated gradients, BN per participant",
        "optimizer": "Adam", "learning_rate": .001, "jit": False,
        "maximum_epochs": 50,
        "early_stopping": {"monitor": "internal_unweighted_validation_loss", "patience": 8,
                           "restore_best_weights": True, "minimum_delta": 0},
        "outer_folds": 5, "inner_early_stop_fraction": .20,
        "fold_assignment": "StratifiedKFold shuffled seed42 on sorted train IDs",
        "inner_assignment": "stratified 20%, random_state 42+fold_index",
        "fold_seed": "42+fold_index, index=1..5",
        "preprocessing": {"sample_rate": 8000, "window_seconds": 5., "overlap": .5,
                          "n_fft": 512, "hop_length": 128, "n_mels": 40,
                          "feature_fmax": 2000, "top_db": 80., "normalization_clip": 5.,
                          "normalization": "per_frequency",
                          "statistics": "fit on all outer-train (fit+early) participants per fold; final on all 568 train"},
        "augmentation": {"scope": "gradient_participants_only", "gain_db": 2.,
                         "time_shift_fraction": .03, "noise_probability": .25,
                         "snr_db_min": 25., "snr_db_max": 35.,
                         "frequency_mask_bins": 2, "frequency_mask_count": 1,
                         "time_mask_frames": 8, "time_mask_count": 1},
        "oof_threshold": {"function": "auriscore.evaluation.select_screening_threshold",
                          "sensitivity_min": .90, "specificity_min": .50,
                          "input": "exactly one genuine outer-fold probability per train participant"},
        "advancement_gate": {"sensitivity_min": .90, "f1_min": .65},
        "final_training": {"init": "from_scratch", "participants": 568,
                           "epochs": "round_half_up(median outer best epochs), clamp 1..50",
                           "early_stop": False},
        "validation": {"once_only_if_gate_passes": True,
                       "threshold": "locked OOF threshold; no validation retuning",
                       "success": "sensitivity>=.90, FP<22, precision>.50, F1>.6471",
                       "attention_diagnostics": "after locked validation metrics only"},
        "comparison_limitation": "H014 threshold was validation-derived; H015 threshold is train-OOF-derived",
        "holdout_policy": "no sealed holdout rows, files, labels, predictions, or scores opened",
        "implementation_sha256": {"trainer": digest(Path(__file__)),
                                  "mil": digest(ROOT / "src/auriscore/mil.py")},
        "environment": {"python": sys.executable, "tensorflow": "2.20.0", "gpu": gpu},
    }


def prepare() -> None:
    if (A / "protocol.json").exists() or R.exists():
        raise RuntimeError("H015 protocol/results already exist; refuse overwrite")
    gpu = gpu_check()
    frame = train_frame()
    preflight = read_json(A / "preflight.json")
    bags = build_bags(frame)
    if len(bags) != 568 or sum(b.recording_count for b in bags) != 2070:
        raise RuntimeError("Bag inventory does not match preflight")
    folds = assignments_for(frame)
    memory_smoke()
    folds.to_csv(A / "fold_assignments.csv", index=False)
    locked = protocol(preflight, digest(A / "fold_assignments.csv"), gpu)
    write_json(A / "protocol.json", locked)
    (A / "protocol.sha256").write_text(digest(A / "protocol.json") + "  protocol.json\n")
    write_json(A / "preflight.json", {**preflight,
        "protocol_status": "locked", "protocol_sha256": digest(A / "protocol.json"),
        "fold_assignments_sha256": digest(A / "fold_assignments.csv"),
        "memory_smoke_batch4": "passed", "cnn_training_started": False})
    print("Protocol SHA256", digest(A / "protocol.json"), flush=True)


def check_lock() -> dict[str, Any]:
    locked = read_json(A / "protocol.json")
    if digest(A / "protocol.json") != (A / "protocol.sha256").read_text().split()[0]:
        raise RuntimeError("Protocol hash mismatch")
    if locked["implementation_sha256"] != {
        "trainer": digest(Path(__file__)), "mil": digest(ROOT / "src/auriscore/mil.py")}:
        raise RuntimeError("Implementation changed after lock; version increment required")
    if digest(A / "fold_assignments.csv") != locked["fold_assignments_sha256"]:
        raise RuntimeError("Fold assignments changed")
    if locked["h014_weights_reused"] or locked["encoder_initialization"] != "from_scratch":
        raise RuntimeError("Encoder initialization lock violated")
    return locked


def norm_config(frame: pd.DataFrame, base: dict[str, Any], path: Path) -> dict[str, Any]:
    if path.exists():
        return read_json(path)
    config = dict(base)
    config["positive_supervision"] = "participant_only_no_recording_labels"
    for key in ("spectrogram_frequency_mean", "spectrogram_frequency_std",
                "spectrogram_statistics_training_frames"):
        config.pop(key, None)
    mean, std, frames = _estimate_frequency_statistics(frame, ROOT, config)
    config.update(spectrogram_frequency_mean=mean, spectrogram_frequency_std=std,
                  spectrogram_statistics_training_frames=frames)
    write_json(path, config)
    return config


def weights_for(bags: list[ParticipantBag]) -> dict[int, float]:
    counts = {c: sum(b.label == c for b in bags) for c in (0, 1)}
    if min(counts.values()) < 1:
        raise RuntimeError("Both classes required")
    return {c: len(bags) / (2 * counts[c]) for c in (0, 1)}


def initialized(seed: int) -> tuple[SiteAwareMIL, tf.keras.optimizers.Optimizer]:
    tf.keras.utils.set_random_seed(seed)
    model = SiteAwareMIL(dropout=.30)
    model((tf.zeros((1, 40, 313, 1)), tf.constant([0]), tf.constant([0])), training=False)
    return model, tf.keras.optimizers.Adam(.001)


def bce(label: int, probability: tf.Tensor) -> tf.Tensor:
    return tf.keras.losses.binary_crossentropy(
        tf.constant([float(label)]), tf.reshape(probability, [1]))


def train_epoch(model: SiteAwareMIL, optimizer: tf.keras.optimizers.Optimizer,
                bags: list[ParticipantBag], loader: BagTensorLoader,
                weights: dict[int, float], seed: int, epoch: int) -> float:
    order = np.random.default_rng(seed + 1009 * epoch).permutation(len(bags))
    losses: list[float] = []
    for start in range(0, len(order), 4):
        group = order[start:start + 4]
        gradients_sum = None
        for raw_index in group:
            index = int(raw_index)
            bag = bags[index]
            x = loader.tensors(bag, training=True,
                               seed=seed * 1000003 + epoch * 10007 + index)
            with tf.GradientTape() as tape:
                probability = model(x, training=True)
                loss = bce(bag.label, probability) * weights[bag.label]
                scaled = loss / len(group)
            gradients = [tf.convert_to_tensor(g) for g in
                         tape.gradient(scaled, model.trainable_variables)]
            gradients_sum = [g if old is None else old + g for old, g in
                             zip(gradients_sum or [None] * len(gradients), gradients)]
            losses.append(float(loss.numpy()))
        optimizer.apply_gradients(zip(gradients_sum, model.trainable_variables))
    return float(np.mean(losses))


def validation_loss(model: SiteAwareMIL, bags: list[ParticipantBag],
                    loader: BagTensorLoader) -> float:
    return float(np.mean([float(bce(b.label, model(
        loader.tensors(b, training=False), training=False)).numpy()) for b in bags]))


def predict(model: SiteAwareMIL, bags: list[ParticipantBag], loader: BagTensorLoader,
            attention: bool = False) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    rows, attention_rows = [], []
    for bag in bags:
        score, weights = model(loader.tensors(bag, training=False),
                               training=False, return_attention=True)
        score = float(score.numpy())
        label = "Present" if bag.label else "Absent"
        rows.append({"participant_id": bag.participant_id, "label": label,
                     "probability": score})
        if attention:
            counts = np.bincount(bag.segment_recording_index,
                                 minlength=bag.recording_count)
            for recording, site, weight, n_segments in zip(
                bag.recording_ids, bag.sites, weights.numpy(), counts):
                attention_rows.append({"participant_id": bag.participant_id,
                    "true_class": label, "probability": score,
                    "recording_id": recording, "site": site,
                    "attention_weight": float(weight),
                    "number_of_segments": int(n_segments)})
    return pd.DataFrame(rows), pd.DataFrame(attention_rows) if attention else None


def score_metrics(table: pd.DataFrame, threshold: float) -> dict[str, Any]:
    y = (table.label == "Present").to_numpy().astype(int)
    scores = table.probability.to_numpy(dtype=float)
    result = metrics(y, (scores >= threshold).astype(int))
    if len(set(y)) == 2:
        result["roc_auc"] = float(roc_auc_score(y, scores))
        result["pr_auc"] = float(average_precision_score(y, scores))
    return result


def run_fold(number: int, assignment: pd.DataFrame,
             bags: dict[str, ParticipantBag], frame: pd.DataFrame,
             base: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    folder = A / "folds" / f"fold-{number}"
    folder.mkdir(parents=True, exist_ok=True)
    predictions_file = folder / "outer_predictions.csv"
    metrics_file = folder / "fold_metrics.json"
    if predictions_file.exists() and metrics_file.exists():
        return pd.read_csv(predictions_file, dtype={"participant_id": str}), read_json(metrics_file)
    subset = assignment[assignment.fold == number]
    ids = {role: subset.loc[subset.role == role, "participant_id"].astype(str).tolist()
           for role in ("fit", "early_stop", "outer_eval")}
    if sum(map(len, ids.values())) != 568:
        raise RuntimeError("Fold membership changed")
    outer_training = set(ids["fit"]) | set(ids["early_stop"])
    outer_frame = frame[frame.subject_group.astype(str).isin(outer_training)]
    config = norm_config(outer_frame, base, folder / "normalization_config.json")
    loader = BagTensorLoader(ROOT, config)
    fit = [bags[x] for x in ids["fit"]]
    early = [bags[x] for x in ids["early_stop"]]
    held = [bags[x] for x in ids["outer_eval"]]
    weights = weights_for(fit)
    model, optimizer = initialized(42 + number)
    epoch_var = tf.Variable(0, dtype=tf.int64, trainable=False)
    checkpoint = tf.train.Checkpoint(model=model, optimizer=optimizer, epoch=epoch_var)
    manager = tf.train.CheckpointManager(checkpoint, str(folder / "checkpoints"), max_to_keep=1)
    state_file = folder / "training_state.json"
    state = read_json(state_file) if state_file.exists() else {
        "epoch": 0, "best_epoch": 0, "best_val_loss": float("inf"), "wait": 0}
    if manager.latest_checkpoint:
        checkpoint.restore(manager.latest_checkpoint).expect_partial()
        if int(epoch_var.numpy()) != state["epoch"]:
            raise RuntimeError("Fold checkpoint/state mismatch")
    elif state["epoch"]:
        raise RuntimeError("Fold state exists without checkpoint")
    best_file = folder / "best.weights.h5"
    first_epoch = 51 if state["wait"] >= 8 else state["epoch"] + 1
    for epoch in range(first_epoch, 51):
        started = time.monotonic()
        train_loss = train_epoch(model, optimizer, fit, loader, weights, 42 + number, epoch)
        val_loss = validation_loss(model, early, loader)
        if val_loss < state["best_val_loss"]:
            state.update(best_epoch=epoch, best_val_loss=val_loss, wait=0)
            model.save_weights(best_file)
        else:
            state["wait"] += 1
        state["epoch"] = epoch
        with (folder / "history.csv").open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "epoch", "loss", "val_loss", "seconds", "best_epoch", "best_val_loss"])
            if stream.tell() == 0:
                writer.writeheader()
            writer.writerow({"epoch": epoch, "loss": train_loss, "val_loss": val_loss,
                             "seconds": time.monotonic() - started,
                             "best_epoch": state["best_epoch"],
                             "best_val_loss": state["best_val_loss"]})
        epoch_var.assign(epoch)
        manager.save(checkpoint_number=epoch)
        write_json(state_file, state)
        status("running", phase="cross_validation", fold=number,
               current_epoch=epoch, best_epoch=state["best_epoch"],
               best_val_loss=state["best_val_loss"])
        print(f"Fold {number}/5 Epoch {epoch}/50 loss={train_loss:.5f} "
              f"val_loss={val_loss:.5f}", flush=True)
        if state["wait"] >= 8:
            break
    if not best_file.exists():
        raise RuntimeError("Missing fold best weights")
    model.load_weights(best_file)
    predictions, _ = predict(model, held, loader)
    predictions["fold"] = number
    predictions.to_csv(predictions_file, index=False)
    result = {"fold": number, "fit_participants": len(fit),
              "early_stop_participants": len(early), "outer_participants": len(held),
              "fit_class_counts": {"Absent": sum(b.label == 0 for b in fit),
                                   "Present": sum(b.label == 1 for b in fit)},
              "participant_class_weights": {"Absent": weights[0], "Present": weights[1]},
              "best_epoch": state["best_epoch"], "best_val_loss": state["best_val_loss"],
              "last_epoch": state["epoch"],
              "normalization_training_participants": len(outer_training),
              "normalization_training_frames": config["spectrogram_statistics_training_frames"],
              "outer_roc_auc": float(roc_auc_score(
                  (predictions.label == "Present").astype(int), predictions.probability)),
              "outer_pr_auc": float(average_precision_score(
                  (predictions.label == "Present").astype(int), predictions.probability))}
    write_json(metrics_file, result)
    plot_history(folder / "history.csv", folder / "training_history.png",
                 f"H015 fold {number} training history", best_epoch=state["best_epoch"])
    tf.keras.backend.clear_session()
    return predictions, result


def plot_history(source: Path, destination: Path, title: str,
                 best_epoch: int | None = None) -> None:
    """Plot only metrics actually present in a saved training history."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    history = pd.read_csv(source)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(history.epoch, history.loss, label="Training loss")
    if "val_loss" in history:
        ax.plot(history.epoch, history.val_loss, label="Internal validation loss")
    if best_epoch is not None:
        ax.axvline(best_epoch, color="gray", linestyle="--",
                   label=f"Best epoch {best_epoch}")
    ax.set(xlabel="Epoch", ylabel="Participant binary cross entropy", title=title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_scores(table: pd.DataFrame, threshold: float, prefix: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, PrecisionRecallDisplay, RocCurveDisplay
    y = (table.label == "Present").astype(int).to_numpy()
    scores = table.probability.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(np.array(score_metrics(table, threshold)["confusion_matrix"]),
                           display_labels=["Absent", "Present"]).plot(ax=ax, colorbar=False)
    ax.set_title(f"H015 {prefix} participant confusion matrix")
    fig.tight_layout()
    fig.savefig(A / f"{prefix}_confusion_matrix.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 5))
    RocCurveDisplay.from_predictions(y, scores, ax=ax)
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Random")
    ax.legend()
    ax.set_title(f"H015 {prefix} participant ROC")
    fig.tight_layout()
    fig.savefig(A / f"{prefix}_roc_curve.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 5))
    PrecisionRecallDisplay.from_predictions(y, scores, ax=ax)
    ax.set_title(f"H015 {prefix} participant precision-recall")
    fig.tight_layout()
    fig.savefig(A / f"{prefix}_precision_recall_curve.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def final_train(frame: pd.DataFrame, bags: dict[str, ParticipantBag],
                base: dict[str, Any], epochs: int) -> tuple[SiteAwareMIL, BagTensorLoader]:
    config = norm_config(frame, base, R / "normalization_config.json")
    loader = BagTensorLoader(ROOT, config)
    all_bags = [bags[k] for k in sorted(bags)]
    weights = weights_for(all_bags)
    model, optimizer = initialized(42)
    epoch_var = tf.Variable(0, dtype=tf.int64, trainable=False)
    checkpoint = tf.train.Checkpoint(model=model, optimizer=optimizer, epoch=epoch_var)
    manager = tf.train.CheckpointManager(checkpoint, str(R / "checkpoints"), max_to_keep=1)
    if manager.latest_checkpoint:
        checkpoint.restore(manager.latest_checkpoint).expect_partial()
    for epoch in range(int(epoch_var.numpy()) + 1, epochs + 1):
        started = time.monotonic()
        loss = train_epoch(model, optimizer, all_bags, loader, weights, 42, epoch)
        with (R / "history.csv").open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["epoch", "loss", "seconds"])
            if stream.tell() == 0:
                writer.writeheader()
            writer.writerow({"epoch": epoch, "loss": loss,
                             "seconds": time.monotonic() - started})
        epoch_var.assign(epoch)
        manager.save(checkpoint_number=epoch)
        status("running", phase="final_training", current_epoch=epoch,
               locked_epochs=epochs)
        print(f"Final Epoch {epoch}/{epochs} loss={loss:.5f}", flush=True)
    model.save(R / "best_model.keras")
    plot_history(R / "history.csv", R / "training_history.png",
                 "H015 final all-train training history")
    write_json(R / "final_training.json", {
        "initialization": "from_scratch", "h014_weights_reused": False,
        "participants": 568, "epochs": epochs,
        "participant_class_weights": {"Absent": weights[0], "Present": weights[1]},
        "normalization_training_frames": config["spectrogram_statistics_training_frames"]})
    return model, loader


def run() -> None:
    gpu_check()
    lock = check_lock()
    if (R / "status.json").exists() and read_json(R / "status.json").get("status") in (
        "completed", "gate_failed"):
        print("H015 already finalized; no duplicate run", flush=True)
        return
    frame = train_frame()
    assignments = pd.read_csv(A / "fold_assignments.csv", dtype={"participant_id": str})
    if not assignments.equals(assignments_for(frame)):
        raise RuntimeError("Fold assignments differ from deterministic lock")
    all_bags = {b.participant_id: b for b in build_bags(frame)}
    if len(all_bags) != 568:
        raise RuntimeError("Participant bags changed")
    if digest(H014 / "config.json") != lock["h014_config_sha256"] or digest(
        H014 / "best_model.keras") != lock["h014_model_sha256"]:
        raise RuntimeError("Frozen H014 artifact changed")
    base = read_json(H014 / "config.json")
    R.mkdir(parents=True, exist_ok=True)
    if not (R / "config.json").exists():
        write_json(R / "config.json", {
            "experiment": NAME, "protocol_sha256": digest(A / "protocol.json"),
            "model": "site-aware participant MIL from scratch",
            "h014_weights_reused": False, "participant_batch_size": 4,
            "tensorflow": tf.__version__, "seed": 42,
            "train_only_cv_folds": 5,
            "validation_policy": "one-time if OOF advancement gate passes",
            "holdout_evaluated": False})
    status("running", phase="cross_validation", current_epoch=0)
    predictions, fold_metrics = [], []
    for fold in range(1, 6):
        p, m = run_fold(fold, assignments, all_bags, frame, base)
        predictions.append(p)
        fold_metrics.append(m)
    oof = pd.concat(predictions, ignore_index=True).sort_values("participant_id")
    if len(oof) != 568 or oof.participant_id.nunique() != 568 or set(
        oof.participant_id) != set(all_bags):
        raise RuntimeError("OOF prediction membership failed")
    oof.to_csv(A / "oof_participant_predictions.csv", index=False)
    proxy = pd.DataFrame({"subject_id": oof.participant_id,
        "subject_group": oof.participant_id, "recording_id": oof.participant_id,
        "label": oof.label, "split": "train"})
    selection = select_screening_threshold(
        proxy, oof.probability.to_numpy(dtype=float), .90, .50)
    threshold = float(selection["threshold"])
    oof_metrics = score_metrics(oof, threshold)
    for fold, (record, prediction) in enumerate(zip(fold_metrics, predictions), start=1):
        operating = score_metrics(prediction, threshold)
        record.update({
            "locked_oof_threshold": threshold,
            "outer_accuracy": operating["accuracy"],
            "outer_precision": operating["precision"],
            "outer_sensitivity": operating["recall_sensitivity"],
            "outer_specificity": operating["specificity"],
            "outer_f1": operating["f1"],
            "outer_balanced_accuracy": operating["balanced_accuracy"],
            "outer_confusion_matrix": operating["confusion_matrix"],
        })
        write_json(A / "folds" / f"fold-{fold}" / "fold_metrics.json", record)
    folds = pd.DataFrame(fold_metrics)
    folds.to_csv(A / "cv_fold_metrics.csv", index=False)
    threshold_record = {"threshold": threshold, "metrics": oof_metrics,
        "target_sensitivity": .90, "minimum_specificity": .50,
        "constraints_met": selection["constraints_met"],
        "candidate_count": selection["candidate_count"],
        "selection_source": "train-only genuine OOF participant probabilities",
        "protocol_sha256": digest(A / "protocol.json")}
    write_json(A / "oof_threshold_lock.json", threshold_record)
    plot_scores(oof, threshold, "oof")
    gate = oof_metrics["recall_sensitivity"] >= .90 and oof_metrics["f1"] >= .65
    summary = {"protocol_sha256": digest(A / "protocol.json"),
        "train_participants": 568, "train_recordings": 2070,
        "fold_sizes": folds.outer_participants.tolist(),
        "best_epochs": folds.best_epoch.tolist(),
        "fold_roc_auc_mean": float(folds.outer_roc_auc.mean()),
        "fold_roc_auc_std": float(folds.outer_roc_auc.std()),
        "fold_pr_auc_mean": float(folds.outer_pr_auc.mean()),
        "fold_pr_auc_std": float(folds.outer_pr_auc.std()),
        "oof_threshold": threshold, "oof_metrics": oof_metrics,
        "advancement_gate": "PASS" if gate else "FAIL", "validation_opened": False,
        "holdout_evaluated": False}
    write_json(A / "cv_summary.json", summary)
    (A / "cv_summary.md").write_text(
        "# H015 train-only CV\n\n" + json.dumps(summary, indent=2) +
        "\n\nOOF is development assessment, not final medical performance.\n")
    if not gate:
        summary["decision"] = "D"
        write_json(A / "summary.json", summary)
        (A / "summary.md").write_text(
            "# H015 decision D\n\nTrain-only OOF gate failed. Validation unopened; H014 retained.\n")
        status("gate_failed", decision="D", validation_opened=False)
        print("H015 decision D: OOF gate failed; validation unopened", flush=True)
        return
    epochs = max(1, min(50, math.floor(statistics.median(
        [int(x) for x in folds.best_epoch]) + .5)))
    write_json(A / "final_training_lock.json", {
        "epochs": epochs, "rule": "round_half_up(median best epochs), clamp 1..50",
        "best_epochs": folds.best_epoch.tolist(), "threshold": threshold,
        "protocol_sha256": digest(A / "protocol.json")})
    status("running", phase="final_training", locked_epochs=epochs)
    model, loader = final_train(frame, all_bags, base, epochs)
    # First validation-row access is after protocol, OOF threshold, gate and final model lock.
    validation_lock = A / "validation_opened.lock.json"
    validation_predictions = A / "validation_participant_predictions.csv"
    validation_attention = A / "validation_attention.csv"
    if validation_predictions.exists() and validation_attention.exists():
        scores = pd.read_csv(validation_predictions, dtype={"participant_id": str})
        attention = pd.read_csv(validation_attention, dtype={"participant_id": str})
    else:
        if validation_lock.exists():
            raise RuntimeError("One-time validation was opened but outputs are incomplete; refuse repeat")
        write_json(validation_lock, {"opened_at": datetime.now(timezone.utc).isoformat(),
            "threshold": threshold, "model_sha256": digest(R / "best_model.keras"),
            "protocol_sha256": digest(A / "protocol.json")})
        status("running", phase="one_time_validation", validation_opened=True)
        val = read_one_split(ROOT / "data/processed/segments.csv", "validation")
        val_bags = build_bags(val)
        if len(val_bags) != 122:
            raise RuntimeError("Validation participant count changed")
        scores, attention = predict(model, val_bags, loader, attention=True)
        scores["predicted_label"] = np.where(scores.probability >= threshold,
                                             "Present", "Absent")
        scores["confusion_group"] = [
            ("TP" if label == "Present" else "FP") if predicted == "Present" else
            ("FN" if label == "Present" else "TN")
            for label, predicted in zip(scores.label, scores.predicted_label)]
        scores.to_csv(validation_predictions, index=False)
        attention = attention.merge(scores[["participant_id", "predicted_label",
                                             "confusion_group"]], on="participant_id",
                                    validate="many_to_one")
        attention.to_csv(validation_attention, index=False)
    val_metrics = score_metrics(scores, threshold)
    write_json(R / "metrics.json", {"threshold": threshold,
        "subject": val_metrics, "validation_participants": 122,
        "threshold_source": "locked train-only OOF", "holdout": {"evaluated": False}})
    plot_scores(scores, threshold, "validation")
    baseline = read_json(H014 / "metrics.json")["validation"]["subject"]
    pd.DataFrame([{"experiment": "H014", **baseline},
                  {"experiment": "H015", **val_metrics}]).to_csv(
                      A / "validation_comparison.csv", index=False)
    _, fp, fn, _ = np.asarray(val_metrics["confusion_matrix"]).ravel()
    _, old_fp, old_fn, _ = np.asarray(baseline["confusion_matrix"]).ravel()
    decision = ("C" if val_metrics["recall_sensitivity"] < .90 else
                "A" if fp < old_fp and val_metrics["precision"] > baseline["precision"]
                and val_metrics["f1"] > baseline["f1"] else "B")
    summary.update({"validation_opened": True, "validation_metrics": val_metrics,
        "h014_metrics": baseline, "decision": decision,
        "h014_vs_h015": {
            "fp_delta": int(fp - old_fp), "fn_delta": int(fn - old_fn),
            "precision_delta": val_metrics["precision"] - baseline["precision"],
            "f1_delta": val_metrics["f1"] - baseline["f1"],
            "sensitivity_delta": val_metrics["recall_sensitivity"] - baseline["recall_sensitivity"]},
        "comparison_limitation": "H014 threshold validation-derived; H015 threshold train-OOF-derived."})
    write_json(A / "summary.json", summary)
    (A / "summary.md").write_text("# H015 site-aware MIL\n\n" +
        json.dumps(summary, indent=2) + "\n\nSealed holdout untouched.\n")
    status("completed", decision=decision, validation_opened=True,
           final_epochs=epochs, threshold=threshold)
    print(f"H015 completed: decision {decision}, confusion {val_metrics['confusion_matrix']}",
          flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.prepare == args.run:
        parser.error("Choose exactly one of --prepare or --run")
    if args.prepare:
        prepare()
    else:
        try:
            run()
        except Exception as error:
            if R.exists():
                status("failed", error=repr(error))
            raise


if __name__ == "__main__":
    main()
