"""H016: fold-local acoustic pretraining, frozen-encoder MIL, gated validation.

Launch this worker detached. Every development partition comes from H015's
saved assignments; validation is inaccessible until the OOF gate passes.
"""
from __future__ import annotations

import argparse
import fcntl
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

import _bootstrap  # noqa: F401
from auriscore.cnn import _dataset, _estimate_frequency_statistics, _participant_weights, build_cnn_model
from auriscore.evaluation import select_screening_threshold
from auriscore.experiment_runtime import best_record, reconcile_history, sync_best_model, training_callbacks
from auriscore.mil import BagTensorLoader, build_bags, read_one_split
from auriscore.pretrained_mil import FrozenSiteAwareMIL, encoder_digest, from_acoustic_model
from train_h015_mil import gpu_check, predict, score_metrics, train_epoch, validation_loss, weights_for

ROOT = Path(__file__).resolve().parents[1]
NAME = "EXP-H016-heart-pretrained-site-aware-mil"
A = ROOT / "analysis" / NAME
R = ROOT / "results" / NAME
H015 = ROOT / "analysis/EXP-H015-heart-site-aware-mil"
H014 = ROOT / "results/EXP-H014-cnn-per-frequency-augmentation-declared-positive-only"
SUPERVISION = ROOT / "analysis/EXP-H014-declared-positive-supervision/training_recording_supervision.csv"
SOURCE_FILES = ["scripts/train_h016_mil.py", "src/auriscore/pretrained_mil.py",
    "scripts/train_h015_mil.py", "src/auriscore/mil.py", "src/auriscore/cnn.py",
    "src/auriscore/augmentation.py", "src/auriscore/spectrogram.py",
    "src/auriscore/evaluation.py", "src/auriscore/experiment_runtime.py"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def status(state: str, **details: Any) -> None:
    write_json(R / "status.json", {"experiment": NAME, "status": state,
        "pid": os.getpid() if state == "running" else None,
        "updated_at": datetime.now(timezone.utc).isoformat(), **details})


def load_training() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read only train rows and H015 train fold metadata; never regenerate folds."""
    frame = read_one_split(ROOT / "data/processed/segments.csv", "train")
    labels = frame[["subject_group", "label"]].drop_duplicates()
    if (len(labels), frame.recording_id.nunique(), len(frame)) != (568, 2070, 15954):
        raise ValueError("Original train inventory changed")
    if labels.label.value_counts().to_dict() != {"Absent": 458, "Present": 110}:
        raise ValueError("Train class inventory changed")
    assignments = pd.read_csv(H015 / "fold_assignments.csv", dtype={"participant_id": str})
    ids = set(labels.subject_group.astype(str))
    held = []
    for fold in range(1, 6):
        subset = assignments[assignments.fold == fold]
        if len(subset) != 568 or subset.participant_id.nunique() != 568 or set(subset.participant_id) != ids:
            raise ValueError("H015 fold partition failed")
        if set(subset.role) != {"fit", "early_stop", "outer_eval"}:
            raise ValueError("H015 fold roles changed")
        held += subset.loc[subset.role == "outer_eval", "participant_id"].tolist()
    if len(held) != 568 or len(set(held)) != 568:
        raise ValueError("Outer fold overlap/missing participants")
    counts = assignments[assignments.role == "outer_eval"].groupby("fold").size().tolist()
    if counts != [114, 114, 114, 113, 113]:
        raise ValueError("H015 outer fold sizes changed")
    audit = pd.read_csv(SUPERVISION, dtype={"subject_group": str, "subject_id": str})
    for row in audit.itertuples(index=False):
        declared = {x.strip().upper() for x in str(row.source_murmur_locations).split("+") if x.strip()}
        expected = ("retained_negative" if row.label == "Absent" else
                    "retained_positive" if str(row.auscultation_location).upper() in declared else
                    "ignored_ambiguous")
        if row.supervision_status != expected or row.label != row.murmur_label:
            raise ValueError("Training supervision no longer agrees with explicit source metadata")
    if audit.recording_id.duplicated().any() or set(audit.recording_id) != set(frame.recording_id):
        raise ValueError("H014 train supervision does not cover original recordings")
    records = frame.groupby("recording_id", as_index=False).agg(
        subject_group=("subject_group", "first"), label=("label", "first"),
        segment_count=("segment_id", "size"))
    check = records.merge(audit, on="recording_id", validate="one_to_one", suffixes=("_actual", "_audit"))
    for field in ("subject_group", "label", "segment_count"):
        if not check[field + "_actual"].astype(str).eq(check[field + "_audit"].astype(str)).all():
            raise ValueError(f"H014 training supervision provenance differs: {field}")
    return frame, assignments, audit


def supervised(frame: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    """Mask ambiguous positive recordings without rewriting original labels."""
    mapping = audit.set_index("recording_id").supervision_status
    states = frame.recording_id.map(mapping)
    if states.isna().any():
        raise ValueError("Recording absent from supervision audit")
    retained = frame.loc[states.isin(["retained_negative", "retained_positive"])].copy()
    if set(retained.subject_group) != set(frame.subject_group):
        raise ValueError("A Stage-1 participant lost all supervised recordings")
    return retained


def partitions(frame: pd.DataFrame, assignment: pd.DataFrame, audit: pd.DataFrame,
               fold: int) -> dict[str, pd.DataFrame]:
    one = assignment[assignment.fold == fold]
    result = {role: frame.loc[frame.subject_group.astype(str).isin(
        one.loc[one.role == role, "participant_id"])].copy()
        for role in ("fit", "early_stop", "outer_eval")}
    result["fit_supervised"] = supervised(result["fit"], audit)
    result["early_supervised"] = supervised(result["early_stop"], audit)
    groups = [set(result[k].subject_group) for k in ("fit", "early_stop", "outer_eval")]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("Participant leakage in H016 partitions")
    return result


def sample_weight_report(frame: pd.DataFrame) -> dict[str, Any]:
    weights = _participant_weights(frame)
    labels = frame[["subject_group", "label"]].drop_duplicates().label.value_counts()
    return {"policy": "equal total participant weight, class balance, normalize mean segment weight to one",
        "participants": int(labels.sum()), "segments": len(frame),
        "raw_participant_class_weights": {k: float(labels.sum() / (2 * v)) for k, v in labels.items()},
        "segment_weight_min": float(weights.min()), "segment_weight_max": float(weights.max()),
        "segment_weight_mean": float(weights.mean())}


def protected_hashes() -> dict[str, str]:
    """Hash only explicit historical experiment paths, never dataset splits."""
    # Do not open H014 validation predictions or figures, even for hashing.
    paths = [H014 / name for name in ("config.json", "best_model.keras", "history.csv", "status.json")]
    paths += list((ROOT / "results/EXP-H015-heart-site-aware-mil").rglob("*"))
    paths += [p for p in H015.rglob("*") if "failure_analysis" not in p.parts]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths) if p.is_file()}


def prepare() -> None:
    if A.exists() or R.exists():
        raise ValueError("H016 already exists; refuse overwrite")
    conclusion = read_json(H015 / "failure_analysis/summary.json")
    if conclusion.get("failure_classification") not in {"B", "C"}:
        raise ValueError("H015 failure-analysis gate does not permit H016")
    gpu = gpu_check()
    frame, assignment, audit = load_training()
    base = read_json(H014 / "config.json")
    if (base["n_mels"], base["cnn_dropout"], base["cnn_learning_rate"], base["cnn_batch_size"]) != (40, .3, .001, 32):
        raise ValueError("H014 acoustic setup changed")
    preflight = []
    for fold in range(1, 6):
        parts = partitions(frame, assignment, audit, fold)
        fit_bags = build_bags(parts["fit"])
        preflight.append({"fold": fold,
            "fit_participants": parts["fit"].subject_group.nunique(),
            "early_participants": parts["early_stop"].subject_group.nunique(),
            "outer_participants": parts["outer_eval"].subject_group.nunique(),
            "stage1_fit_supervised_recordings": parts["fit_supervised"].recording_id.nunique(),
            "stage1_fit_supervised_segments": len(parts["fit_supervised"]),
            "stage1_early_supervised_segments": len(parts["early_supervised"]),
            "stage1_sample_weights": sample_weight_report(parts["fit_supervised"]),
            "stage2_class_weights": weights_for(fit_bags)})
    A.mkdir(parents=True)
    fold_ref = {"path": str((H015 / "fold_assignments.csv").relative_to(ROOT)),
                "sha256": sha(H015 / "fold_assignments.csv"),
                "fold_sizes": [114, 114, 114, 113, 113], "regenerated": False}
    write_json(A / "fold_assignments_reference.json", fold_ref)
    write_json(A / "preflight.json", {"train_participants": 568, "present": 110,
        "absent": 458, "recordings": 2070, "segments": 15954,
        "stage1_supervised_segments": len(supervised(frame, audit)),
        "stage2_all_recordings_retained": True, "folds": preflight,
        "validation_opened": False, "holdout_opened": False})
    write_json(A / "historical_artifact_hashes.json", protected_hashes())
    config = {
        "version": 1, "experiment": NAME, "created_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Fold-local supervised acoustic learning followed by frozen-encoder MIL improves H015 train OOF ranking",
        "h015_failure_classification": conclusion["failure_classification"],
        "h015_failure_summary_sha256": sha(H015 / "failure_analysis/summary.json"),
        "outer_folds": "existing H015 folds", "outer_fold_count": 5,
        "fold_assignments": fold_ref, "inner_split": "reuse H015 saved fit/early_stop roles exactly",
        "master_seed": 42, "fold_seed": "42 + fold index (1..5); reset separately for Stage 1 and Stage 2",
        "stage1_encoder_initialization": "from_scratch", "h014_weights_reused": False,
        "stage1_supervision": "H014_declared_positive_only",
        "stage1_internal_loss_supervision": "same retained-negative/declared-positive mask; ambiguous positives ignored",
        "stage1_architecture": "H014 compact CNN Conv16/32/64-BN-ReLU-MaxPool, GAP64, Dropout(.30), sigmoid",
        "input_shape": [40, 313, 1], "window_seconds": 5., "n_mels": 40,
        "preprocessing_reference": "H014 config values excluding full-train normalization statistics",
        "preprocessing_config_sha256": sha(H014 / "config.json"),
        "normalization": "per_frequency; Stage-1 gradient-update retained supervised segments only; internal/outer excluded",
        "final_normalization": "all retained supervised TRAIN segments only",
        "stage1_segment_batch_size": 32, "stage1_weighting": "auriscore.cnn._participant_weights unchanged",
        "stage1_internal_loss_weighting": "same H014 sample weighting computed within internal supervised subset",
        "stage2_encoder_frozen": True, "stage2_encoder_execution": "inference mode, including BatchNorm and encoder dropout",
        "stage2_participant_supervision": True, "recording_supervision_stage2": False,
        "stage2_bags": "all eligible recordings including outside-declared Present recordings",
        "segment_to_recording": "mean of all segment embeddings",
        "site_vocabulary": ["AV", "MV", "PV", "TV", "Phc", "UNKNOWN"],
        "site_embedding_dim": 8, "attention_hidden_dim": 32, "classifier_hidden_dim": 32,
        "attention": "Dense32 relu, Dropout .30, Dense1 linear, masked softmax; acoustic64 values only",
        "classifier": "Dense32 relu, Dropout .30, Dense1 sigmoid",
        "participant_batch_size": 4, "participant_batch_implementation": "H015 sequential microbatches and gradient accumulation",
        "stage2_weighting": "N/(2*N_c) based on fit participants", "stage2_loss": "participant BCE",
        "stage2_internal_loss": "unweighted participant BCE as H015",
        "augmentation": "exact H011/H014 conservative policy in both stages, gradient-update participants only",
        "augmentation_parameters": {k: v for k, v in base.items() if k.startswith("augmentation_")},
        "optimizer": "Adam", "learning_rate": .001, "dropout": .30, "jit_compile": False,
        "max_epochs_per_stage": 50, "patience_per_stage": 8, "restore_best_weights": True,
        "threshold_policy": "existing auriscore.evaluation.select_screening_threshold on 568 OOF scores",
        "threshold_sensitivity_min": .90, "threshold_specificity_min": .50,
        "advancement_gate": {"sensitivity_min": .90, "f1_min": .65, "roc_auc_min": .70},
        "final_training": "from scratch Stage 1 on all eligible train supervision, then freeze encoder and Stage 2 on all568; each stage uses rounded median fold best epoch, clamped1..50",
        "validation": "exactly once after gate/model/threshold lock; fixed OOF threshold; never used for early stopping",
        "decision_A": "validation sensitivity>=.90 and FP<22 and precision>.50 and F1>.6471",
        "decision_B": "validation sensitivity>=.90 without clear H014 improvement",
        "decision_C": "validation sensitivity<.90", "decision_D": "any OOF mandatory gate fails",
        "desirable_engineering_targets": {"sensitivity": .90, "specificity": .85,
                                           "precision": .65, "f1": .75},
        "holdout": "never opened, enumerated, scored or evaluated",
        "train_segments_sha256": hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
        "train_supervision_audit_sha256": sha(SUPERVISION),
        "implementation_sha256": {p: sha(ROOT / p) for p in SOURCE_FILES},
        "historical_artifact_manifest_sha256": sha(A / "historical_artifact_hashes.json"),
        "environment": {"tensorflow": "2.20.0", "gpu": gpu, "python": sys.executable},
    }
    write_json(A / "protocol.json", config)
    (A / "protocol_sha256.txt").write_text(sha(A / "protocol.json") + "\n")
    print("H016 protocol locked:", sha(A / "protocol.json"), flush=True)


def verify_lock(frame: pd.DataFrame) -> dict[str, Any]:
    protocol = read_json(A / "protocol.json")
    if sha(A / "protocol.json") != (A / "protocol_sha256.txt").read_text().strip():
        raise ValueError("Protocol hash mismatch")
    if any(sha(ROOT / p) != value for p, value in protocol["implementation_sha256"].items()):
        raise ValueError("Implementation changed after protocol lock")
    if sha(H015 / "fold_assignments.csv") != protocol["fold_assignments"]["sha256"]:
        raise ValueError("H015 fold assignments changed")
    if sha(SUPERVISION) != protocol["train_supervision_audit_sha256"]:
        raise ValueError("Train supervision audit changed")
    if sha(H015 / "failure_analysis/summary.json") != protocol["h015_failure_summary_sha256"]:
        raise ValueError("H015 failure-analysis conclusion changed after H016 lock")
    if hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest() != protocol["train_segments_sha256"]:
        raise ValueError("Train data provenance changed")
    for p, value in read_json(A / "historical_artifact_hashes.json").items():
        if sha(ROOT / p) != value:
            raise ValueError(f"Historical artifact changed: {p}")
    return protocol


def fitted_config(fit: pd.DataFrame, folder: Path, seed: int) -> dict[str, Any]:
    destination = folder / "normalization_config.json"
    if destination.exists():
        return read_json(destination)
    config = read_json(H014 / "config.json")
    config.update(seed=seed, experiment_name=NAME)
    for key in ("spectrogram_frequency_mean", "spectrogram_frequency_std", "spectrogram_statistics_training_frames"):
        config.pop(key, None)
    mean, std, frames = _estimate_frequency_statistics(fit, ROOT, config)
    config.update(spectrogram_frequency_mean=mean, spectrogram_frequency_std=std,
                  spectrogram_statistics_training_frames=frames)
    write_json(destination, config)
    return config


def history_plot(folder: Path, title: str, best_epoch: int | None = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    table = pd.read_csv(folder / "history.csv")
    rows = 2 if "accuracy" in table else 1
    fig, axes = plt.subplots(rows, 1, figsize=(8, 4 * rows), squeeze=False)
    for axis, metric in zip(axes[:, 0], ["loss", "accuracy"]):
        axis.plot(table.epoch, table[metric], label="Training")
        if "val_" + metric in table:
            axis.plot(table.epoch, table["val_" + metric], label="Internal early-stop subset")
        if best_epoch:
            axis.axvline(best_epoch, color="gray", linestyle="--", label=f"Best epoch {best_epoch}")
        axis.set(xlabel="Epoch", ylabel=metric.capitalize(), title=title)
        axis.legend()
    fig.tight_layout()
    fig.savefig(folder / "training_history.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


class StageProgress(tf.keras.callbacks.Callback):
    def __init__(self, stage: str, fold: int | str):
        super().__init__()
        self.stage, self.fold = stage, fold

    def on_epoch_begin(self, epoch: int, logs: Any = None) -> None:
        status("running", stage=self.stage, fold=self.fold, current_epoch=epoch + 1)


def stage1(fit: pd.DataFrame, early: pd.DataFrame | None, folder: Path,
           seed: int, fold: int | str, fixed_epochs: int | None = None) -> tuple[tf.keras.Model, dict[str, Any], dict[str, Any]]:
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "completed.json").exists():
        return (tf.keras.models.load_model(folder / "best_model.keras"),
                read_json(folder / "normalization_config.json"), read_json(folder / "completed.json"))
    config = fitted_config(fit, folder, seed)
    tf.keras.utils.set_random_seed(seed)
    model = build_cnn_model((40, 313, 1), config, jit_compile=False)
    previous = reconcile_history(folder)
    write_json(folder / "status.json", {"status": "running", "stage": "stage1", "fold": fold})
    print(f"H016 Stage 1 fold={fold}; fit participants={fit.subject_group.nunique()} segments={len(fit)}", flush=True)
    if early is not None:
        best_epoch, best_loss, wait = best_record(previous)
        if len(previous) < 50 and wait < 8:
            model.fit(_dataset(fit, ROOT, config, True, True),
                validation_data=_dataset(early, ROOT, config, False, True), epochs=50,
                callbacks=training_callbacks(tf, folder, 8, previous) + [StageProgress("stage1", fold)],
                shuffle=False, verbose=2)
        table = reconcile_history(folder)
        best_epoch, best_loss, _ = sync_best_model(folder, table)
        model = tf.keras.models.load_model(folder / "best_model.keras")
    else:
        if fixed_epochs is None:
            raise ValueError("Final Stage 1 epoch count must be locked")
        (folder / "checkpoints").mkdir(exist_ok=True)
        if len(previous) < fixed_epochs:
            callbacks = [
                tf.keras.callbacks.CSVLogger(str(folder / "checkpoints/keras_history.csv"), append=not previous.empty),
                tf.keras.callbacks.ModelCheckpoint(str(folder / "last_model.keras")),
                tf.keras.callbacks.BackupAndRestore(str(folder / "checkpoints/backup"),
                    save_freq="epoch", double_checkpoint=True, delete_checkpoint=False),
                StageProgress("stage1_final", fold)]
            model.fit(_dataset(fit, ROOT, config, True, True), epochs=fixed_epochs,
                      callbacks=callbacks, shuffle=False, verbose=2)
        table = reconcile_history(folder)
        model = tf.keras.models.load_model(folder / "last_model.keras")
        model.save(folder / "best_model.keras")
        best_epoch, best_loss = fixed_epochs, None
    acoustic = tf.keras.Model(model.input, model.layers[-2].output)
    result = {"fold": fold, "best_epoch": int(best_epoch), "best_internal_loss": best_loss,
        "epochs": len(table), "encoder_sha256": encoder_digest(acoustic),
        "normalization_sha256": sha(folder / "normalization_config.json"),
        "normalization_participants": int(fit.subject_group.nunique()),
        "normalization_segments": len(fit), "sample_weights": sample_weight_report(fit),
        "initialization": "from_scratch", "h014_weights_reused": False}
    write_json(folder / "completed.json", result)
    history_plot(folder, f"H016 Stage 1 fold {fold}", int(best_epoch) if early is not None else None)
    write_json(folder / "status.json", {"status": "completed", **result})
    return model, config, result


def stage2(acoustic: tf.keras.Model, config: dict[str, Any], fit: pd.DataFrame,
           early: pd.DataFrame | None, folder: Path, seed: int, fold: int | str,
           fixed_epochs: int | None = None) -> tuple[FrozenSiteAwareMIL, dict[str, Any]]:
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "completed.json").exists():
        return tf.keras.models.load_model(folder / "best_model.keras"), read_json(folder / "completed.json")
    model = from_acoustic_model(acoustic, seed)
    original_encoder = encoder_digest(model.segment_encoder)
    optimizer = tf.keras.optimizers.Adam(.001)
    optimizer.build(model.trainable_variables)
    checkpoint = tf.train.Checkpoint(model=model, optimizer=optimizer)
    manager = tf.train.CheckpointManager(checkpoint, str(folder / "checkpoints"), max_to_keep=3)
    state_file = folder / "training_state.json"
    state = read_json(state_file) if state_file.exists() else {
        "epoch": 0, "best_epoch": 0, "best_loss": None, "wait": 0, "history": [], "checkpoint": None}
    if state["checkpoint"]:
        checkpoint.restore(state["checkpoint"]).assert_existing_objects_matched()
    fit_bags = build_bags(fit)
    early_bags = build_bags(early) if early is not None else None
    weights = weights_for(fit_bags)
    loader = BagTensorLoader(ROOT, config)
    limit = 50 if early is not None else int(fixed_epochs)
    first = limit + 1 if early is not None and state["wait"] >= 8 else state["epoch"] + 1
    for epoch in range(first, limit + 1):
        status("running", stage="stage2", fold=fold, current_epoch=epoch)
        print(f"H016 Stage 2 fold={fold} Epoch {epoch}/{limit}", flush=True)
        started = time.monotonic()
        loss = train_epoch(model, optimizer, fit_bags, loader, weights, seed, epoch)
        val_loss = validation_loss(model, early_bags, loader) if early_bags is not None else None
        improved = early is None or state["best_loss"] is None or val_loss < state["best_loss"]
        if improved:
            state.update(best_epoch=epoch, best_loss=val_loss, wait=0)
            best_path = folder / f"best-epoch-{epoch:04d}.weights.h5"
            model.save_weights(best_path)
            state["best_weights"] = str(best_path)
        else:
            state["wait"] += 1
        if encoder_digest(model.segment_encoder) != original_encoder:
            raise RuntimeError("Stage-2 encoder changed despite freeze")
        state["epoch"] = epoch
        row = {"epoch": epoch, "loss": loss, "seconds": time.monotonic() - started}
        if val_loss is not None:
            row["val_loss"] = val_loss
        state["history"].append(row)
        state["checkpoint"] = manager.save(checkpoint_number=epoch)
        write_json(state_file, state)  # Commit only after recoverable model/optimizer exist.
        pd.DataFrame(state["history"]).to_csv(folder / "history.csv", index=False)
        write_json(folder / "status.json", {"status": "running", "epoch": epoch,
            "best_epoch": state["best_epoch"], "best_val_loss": state["best_loss"]})
        print(f"loss={loss:.6f} internal_loss={val_loss}", flush=True)
        if early is not None and state["wait"] >= 8:
            break
    model.load_weights(state["best_weights"])
    if encoder_digest(model.segment_encoder) != original_encoder:
        raise RuntimeError("Restored Stage-2 best model changed encoder")
    model.save(folder / "best_model.keras")
    result = {"fold": fold, "best_epoch": state["best_epoch"],
        "best_internal_loss": state["best_loss"], "epochs": state["epoch"],
        "participant_class_weights": {"Absent": weights[0], "Present": weights[1]},
        "fit_participants": len(fit_bags), "encoder_sha256": original_encoder,
        "encoder_frozen_verified_each_epoch": True}
    write_json(folder / "completed.json", result)
    history_plot(folder, f"H016 Stage 2 fold {fold}", state["best_epoch"] if early is not None else None)
    write_json(folder / "status.json", {"status": "completed", **result})
    return model, result


def score_plots(scores: pd.DataFrame, threshold: float, tag: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay, PrecisionRecallDisplay, RocCurveDisplay
    y = scores.label.eq("Present").astype(int).to_numpy()
    p = scores.probability.to_numpy()
    for kind in ("confusion_matrix", "roc_curve", "precision_recall_curve"):
        fig, axis = plt.subplots(figsize=(7, 5))
        if kind == "confusion_matrix":
            ConfusionMatrixDisplay(np.asarray(score_metrics(scores, threshold)["confusion_matrix"]),
                display_labels=["Absent", "Present"]).plot(ax=axis, colorbar=False)
        elif kind == "roc_curve":
            RocCurveDisplay.from_predictions(y, p, ax=axis)
            axis.plot([0, 1], [0, 1], "--", color="gray", label="Random")
            axis.legend()
        else:
            PrecisionRecallDisplay.from_predictions(y, p, ax=axis)
        axis.set_title(f"H016 {tag} participant {kind.replace('_', ' ')}")
        fig.tight_layout()
        fig.savefig(A / f"{tag}_{kind}.png", dpi=180, bbox_inches="tight")
        plt.close(fig)


def gate_passes(measured: dict[str, Any]) -> bool:
    return (measured["recall_sensitivity"] >= .90 and measured["f1"] >= .65
            and measured["roc_auc"] >= .70)


def verify_unchanged() -> None:
    for path, expected in read_json(A / "historical_artifact_hashes.json").items():
        if sha(ROOT / path) != expected:
            raise RuntimeError(f"Historical artifact changed: {path}")


def finalize(summary: dict[str, Any]) -> None:
    verify_unchanged()
    summary.update(h014_unchanged=True, h015_unchanged=True, h014_weights_reused=False,
                   sealed_holdout_untouched=True)
    write_json(A / "summary.json", summary)
    (A / "summary.md").write_text("# H016 two-stage site-aware MIL\n\n" +
        f"Decision {summary['decision']}.\n\n" + json.dumps(summary, indent=2) + "\n\n" +
        "H014 threshold used development validation; H016 threshold was locked from train-only OOF. "
        "These are development estimates, not clinical performance claims.\n")
    status("gate_failed" if summary["decision"] == "D" else "completed",
           decision=summary["decision"], validation_opened=summary["validation_opened"])
    print(json.dumps(summary, indent=2), flush=True)


def run() -> None:
    gpu_check()
    frame, assignments, audit = load_training()
    protocol = verify_lock(frame)
    if (R / "status.json").exists() and read_json(R / "status.json")["status"] in {"completed", "gate_failed"}:
        print("H016 already finalized; skipping", flush=True)
        return
    R.mkdir(parents=True, exist_ok=True)
    if not (R / "config.json").exists():
        write_json(R / "config.json", protocol)
    status("running", stage="preflight", current_epoch=0, validation_opened=False)
    stage1_rows, stage2_rows, outer_scores = [], [], []
    for fold in range(1, 6):
        folder = R / "folds" / f"fold-{fold}"
        parts = partitions(frame, assignments, audit, fold)
        acoustic, config, s1 = stage1(parts["fit_supervised"], parts["early_supervised"],
            folder / "stage1", 42 + fold, fold)
        mil, s2 = stage2(acoustic, config, parts["fit"], parts["early_stop"],
            folder / "stage2", 42 + fold, fold)
        output = folder / "outer_predictions.csv"
        if output.exists():
            scores = pd.read_csv(output, dtype={"participant_id": str}, float_precision="round_trip")
        else:
            marker = folder / "outer_evaluation_started.json"
            if marker.exists():
                raise RuntimeError("Interrupted outer evaluation has no committed predictions; refuse silent repeat")
            write_json(marker, {"fold": fold, "model_sha256": sha(folder / "stage2/best_model.keras")})
            scores, _ = predict(mil, build_bags(parts["outer_eval"]), BagTensorLoader(ROOT, config))
            scores["fold"] = fold
            scores.to_csv(output, index=False)
        outer_scores.append(scores)
        stage1_rows.append(s1)
        stage2_rows.append(s2)
        pd.DataFrame(stage1_rows).to_csv(A / "stage1_fold_metrics.csv", index=False)
        pd.DataFrame(stage2_rows).to_csv(A / "stage2_fold_metrics.csv", index=False)
        tf.keras.backend.clear_session()
    oof = pd.concat(outer_scores, ignore_index=True).sort_values("participant_id")
    if len(oof) != 568 or oof.participant_id.nunique() != 568 or set(oof.participant_id) != set(frame.subject_group):
        raise ValueError("OOF participant membership invalid")
    held = assignments[assignments.role == "outer_eval"]
    aligned = oof.merge(held, on=["participant_id", "fold"], suffixes=("", "_reference"), validate="one_to_one")
    if len(aligned) != 568 or not aligned.label.eq(aligned.label_reference).all():
        raise ValueError("OOF folds/labels misaligned")
    oof.to_csv(A / "oof_participant_predictions.csv", index=False)
    proxy = pd.DataFrame({"subject_id": oof.participant_id, "subject_group": oof.participant_id,
        "recording_id": oof.participant_id, "label": oof.label, "split": "train"})
    selected = select_screening_threshold(proxy, oof.probability.to_numpy(), .90, .50)
    threshold = float(selected["threshold"])
    measured = score_metrics(oof, threshold)
    for row, scores in zip(stage2_rows, outer_scores, strict=True):
        row["outer_metrics_at_locked_oof_threshold"] = score_metrics(scores, threshold)
    pd.DataFrame(stage2_rows).to_csv(A / "stage2_fold_metrics.csv", index=False)
    h015_metrics = read_json(H015 / "summary.json")["oof_metrics"]
    pd.DataFrame([{"experiment": "H015", **h015_metrics},
                  {"experiment": "H016", **measured}]).to_csv(A / "h015_vs_h016_oof.csv", index=False)
    lock = {"threshold": threshold, "metrics": measured, "policy": selected,
            "source": "568 genuine train OOF participant probabilities",
            "protocol_sha256": sha(A / "protocol.json")}
    write_json(A / "oof_threshold_lock.json", lock)
    write_json(R / "metrics.json", {"scope": "train_only_oof", "threshold": threshold,
        "oof": measured, "holdout": {"evaluated": False}, "validation_opened": False})
    score_plots(oof, threshold, "oof")
    summary = {"experiment": NAME, "protocol_sha256": sha(A / "protocol.json"),
        "h015_failure_classification": protocol["h015_failure_classification"],
        "stage1_fold_best_epochs": [x["best_epoch"] for x in stage1_rows],
        "stage2_fold_best_epochs": [x["best_epoch"] for x in stage2_rows],
        "oof_threshold": threshold, "oof_metrics": measured,
        "h015_oof_metrics": h015_metrics,
        "advancement_gate": "PASS" if gate_passes(measured) else "FAIL", "validation_opened": False}
    write_json(A / "cv_summary.json", summary)
    (A / "cv_summary.md").write_text("# H016 train-only OOF assessment\n\n" + json.dumps(summary, indent=2) + "\n")
    if not gate_passes(measured):
        summary["decision"] = "D"
        finalize(summary)
        return
    epochs1 = max(1, min(50, math.floor(statistics.median(summary["stage1_fold_best_epochs"]) + .5)))
    epochs2 = max(1, min(50, math.floor(statistics.median(summary["stage2_fold_best_epochs"]) + .5)))
    write_json(A / "final_training_lock.json", {"stage1_epochs": epochs1, "stage2_epochs": epochs2,
        "threshold": threshold, "protocol_sha256": sha(A / "protocol.json")})
    acoustic, config, s1 = stage1(supervised(frame, audit), None, R / "final/stage1", 42, "final", epochs1)
    mil, s2 = stage2(acoustic, config, frame, None, R / "final/stage2", 42, "final", epochs2)
    marker = A / "validation_opened.lock.json"
    output = A / "validation_participant_predictions.csv"
    attention_path = A / "validation_attention.csv"
    if output.exists() and attention_path.exists():
        validation_scores = pd.read_csv(output, dtype={"participant_id": str}, float_precision="round_trip")
    else:
        if marker.exists():
            raise RuntimeError("Validation was opened without complete artifacts; refuse repeat")
        write_json(marker, {"threshold": threshold, "model_sha256": sha(R / "final/stage2/best_model.keras"),
                           "opened_at": datetime.now(timezone.utc).isoformat()})
        status("running", stage="one_time_validation", validation_opened=True)
        validation = read_one_split(ROOT / "data/processed/segments.csv", "validation")
        labels = validation[["subject_group", "label"]].drop_duplicates()
        if len(labels) != 122 or set(labels.subject_group) & set(frame.subject_group):
            raise ValueError("Validation membership/leakage check failed")
        if labels.label.value_counts().to_dict() != {"Absent": 98, "Present": 24}:
            raise ValueError("Validation class counts changed")
        validation_scores, attention = predict(mil, build_bags(validation), BagTensorLoader(ROOT, config), attention=True)
        validation_scores["predicted_label"] = np.where(validation_scores.probability >= threshold, "Present", "Absent")
        validation_scores["confusion_group"] = [
            ("TP" if label == "Present" else "FP") if pred == "Present" else
            ("FN" if label == "Present" else "TN") for label, pred in
            zip(validation_scores.label, validation_scores.predicted_label)]
        validation_scores.to_csv(output, index=False)
        attention.merge(validation_scores[["participant_id", "predicted_label", "confusion_group"]],
            on="participant_id", validate="many_to_one").to_csv(attention_path, index=False)
    validation_metrics = score_metrics(validation_scores, threshold)
    write_json(R / "metrics.json", {"threshold": threshold, "validation": validation_metrics,
                                   "holdout": {"evaluated": False}})
    score_plots(validation_scores, threshold, "validation")
    baseline = read_json(H014 / "metrics.json")["validation"]["subject"]
    pd.DataFrame([{"experiment": "H014", **baseline}, {"experiment": "H016", **validation_metrics}]).to_csv(
        A / "h014_vs_h016.csv", index=False)
    _, fp, fn, _ = np.asarray(validation_metrics["confusion_matrix"]).ravel()
    _, old_fp, old_fn, _ = np.asarray(baseline["confusion_matrix"]).ravel()
    decision = "C" if validation_metrics["recall_sensitivity"] < .90 else (
        "A" if fp < 22 and validation_metrics["precision"] > .50 and validation_metrics["f1"] > .6471 else "B")
    summary.update(decision=decision, validation_opened=True, validation_metrics=validation_metrics,
        h014_vs_h016_delta={**{k: validation_metrics[k] - baseline[k] for k in (
            "accuracy", "precision", "recall_sensitivity", "specificity", "f1", "balanced_accuracy", "roc_auc", "pr_auc")},
            "FP": int(fp - old_fp), "FN": int(fn - old_fn)})
    finalize(summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.prepare == args.run:
        parser.error("Choose --prepare or --run")
    if args.prepare:
        prepare()
        return
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with (ROOT / ".runtime/h016-worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            run()
        except Exception as error:
            if R.exists():
                status("failed", error=repr(error))
            raise


if __name__ == "__main__":
    main()
