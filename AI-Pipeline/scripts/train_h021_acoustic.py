"""Detached, resumable TRAIN-only H021 fold-local acoustic hard-negative mining."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

import _bootstrap  # noqa: F401
from auriscore.cnn import _dataset, _estimate_frequency_statistics, build_cnn_model
from auriscore.experiment_runtime import best_record, reconcile_history, sync_best_model, training_callbacks
from auriscore.hard_negative_mining import inner_assignments, inner_fit_early, select_hard_negatives
from auriscore.linear_head import C_GRID, FEATURES, choose_c, make_classifier
from auriscore.mil import BagTensorLoader, build_bags
from auriscore.oof_audit import best_at_sensitivity, sha256, threshold_tradeoff, verify_train_oof
from auriscore.pretrained_mil import encoder_digest
from train_h015_mil import gpu_check
from train_h016_mil import load_training, partitions, supervised, history_plot

ROOT = Path(__file__).resolve().parents[1]
NAME = "EXP-H021-fold-local-hard-negative-acoustic-mining"
A = ROOT / "analysis" / NAME
R = ROOT / "results" / NAME
H014 = ROOT / "results/EXP-H014-cnn-per-frequency-augmentation-declared-positive-only"
H015 = ROOT / "analysis/EXP-H015-heart-site-aware-mil"
H020 = ROOT / "analysis/EXP-H020-linear-participant-head"
SOURCE = ["scripts/train_h021_acoustic.py", "src/auriscore/hard_negative_mining.py",
          "src/auriscore/linear_head.py", "src/auriscore/cnn.py"]


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(path)


def state(status: str, **details) -> None:
    write(R / "status.json", {"experiment": NAME, "status": status,
        "pid": os.getpid() if status == "running" else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "external_validation_opened": False, "sealed_test_opened": False, **details})


def preflight():
    frame, assignments, audit = load_training()
    inventory = pd.read_csv(H015 / "train_bag_inventory.csv", dtype={"participant_id": str})
    h020 = read(H020 / "metrics.json")
    precheck = read(H020 / "representation_precheck/summary.json")
    if h020["confusion_matrix"] != [[279, 179], [11, 99]] or h020["external_validation_opened"] or h020["sealed_test_opened"]:
        raise ValueError("H020 reference or data boundary changed")
    if precheck["fp_at_least_one_present_neighbor_5nn"] < 1 or precheck["external_validation_opened"] or precheck["sealed_test_opened"]:
        raise ValueError("H020 precheck does not support H021")
    verify_train_oof(pd.read_csv(H020 / "predictions_oof.csv", dtype={"participant_id": str}), assignments, inventory)
    if read(H014 / "config.json").get("cnn_architecture", "compact") != "compact":
        raise ValueError("H014 acoustic topology changed")
    return frame, assignments, audit, inventory


def smoke() -> None:
    """Tiny real TRAIN fit-only gradient and serialization probe; no selection result."""
    gpu = gpu_check()
    frame, assignments, audit, _ = preflight()
    subset = supervised(frame.loc[frame.subject_group.astype(str).isin(set(assignments.loc[(assignments.fold == 1) & assignments.role.eq("fit"), "participant_id"]))], audit)
    chosen = []
    for label in ("Absent", "Present"):
        people = subset.loc[subset.label == label, "subject_group"].drop_duplicates().iloc[:2]
        for person in people:
            chosen.append(subset.loc[subset.subject_group == person].iloc[0])
    tiny = pd.DataFrame(chosen).reset_index(drop=True)
    assert len(tiny) == 4 and tiny.label.value_counts().to_dict() == {"Absent": 2, "Present": 2}
    config = read(H014 / "config.json")
    config["cnn_batch_size"] = 4
    multiplier = {str(r.recording_id): 1.0 for r in tiny.itertuples()}
    neg_id = str(tiny.loc[tiny.label == "Absent", "recording_id"].iloc[0])
    multiplier[neg_id] = 2.0
    ds = _dataset(tiny, ROOT, config, False, True, multiplier)
    x, y, weights = next(iter(ds))
    got = {str(r.recording_id): float(weights[i].numpy()) for i, r in enumerate(tiny.itertuples())}
    if not np.isclose(got[neg_id], 2.0) or not all(np.isclose(v, 1.0) for k, v in got.items() if k != neg_id):
        raise ValueError("H021 2.0/1.0 recording multipliers did not enter Stage-1 dataset")
    model = build_cnn_model((40, 313, 1), config, jit_compile=False)
    with tf.GradientTape() as tape:
        p = model(x, training=True)
        losses = tf.keras.losses.binary_crossentropy(y[:, None], p)
        loss = tf.reduce_sum(losses * weights) / tf.reduce_sum(weights)
    gradients = tape.gradient(loss, model.trainable_variables)
    if not np.isfinite(float(loss.numpy())) or any(g is None or not np.isfinite(g.numpy()).all() for g in gradients):
        raise ValueError("Nonfinite or disconnected Stage-1 gradient")
    probe = ROOT / ".runtime/h021-smoke.keras"
    probe.parent.mkdir(parents=True, exist_ok=True)
    model.save(probe)
    loaded = tf.keras.models.load_model(probe)
    encoder = tf.keras.Model(loaded.input, loaded.layers[-2].output)
    features = encoder(x, training=False).numpy()
    linear = make_classifier(1.0, 42)
    linear.fit(features, y.numpy().astype(int))
    if features.shape != (4, 64) or not np.isfinite(linear.predict_proba(features)).all():
        raise ValueError("Encoder-to-H020 linear path failed")
    probe.unlink()
    print(json.dumps({"smoke_pass": True, "gpu": gpu, "tensorflow": tf.__version__,
                      "weights": got, "weighted_loss": float(loss.numpy()),
                      "gradient_tensors": len(gradients), "encoder_shape": list(features.shape)}))


def prepare() -> None:
    if A.exists() or R.exists():
        raise FileExistsError("H021 exists; do not overwrite")
    gpu = gpu_check()
    frame, assignments, audit, inventory = preflight()
    config = {"experiment": NAME, "version": 1, "source": "H020", "seed": 42,
              "outer_folds": 5, "inner_mining_folds": 5, "hard_negative_unit": "recording",
              "hard_negative_fraction": .20, "hard_negative_multiplier": 2.0,
              "ordinary_multiplier": 1.0, "stage1_fit_roles": "saved H015 fit/early_stop",
              "stage1_early_stop_patience": 8, "stage1_max_epochs": 50,
              "inner_early_stop_fraction": .20,
              "stage1_base_config_sha256": sha256(H014 / "config.json"),
              "stage1_supervision_sha256": sha256(ROOT / "analysis/EXP-H014-declared-positive-supervision/training_recording_supervision.csv"),
              "fold_assignments_sha256": sha256(H015 / "fold_assignments.csv"),
              "train_inventory_sha256": sha256(H015 / "train_bag_inventory.csv"),
              "train_segments_sha256": hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
              "h020_protocol_sha256": sha256(H020 / "protocol.json"),
              "C_grid": list(C_GRID), "class_weight": "balanced",
              "normalization": "fit Stage-1 gradient segments only in each inner and outer model",
              "aggregation": "segment mean to recording, recording mean to participant",
              "threshold": "OOF sensitivity>=0.90, max F1, then specificity, precision",
              "external_validation": "closed", "sealed_test": "closed"}
    protocol = {"experiment": NAME, "hypothesis": "fold-local hard-negative emphasis improves acoustic representation and reduces H020 false positives",
                "source_experiment": "EXP-H020-linear-participant-head",
                "outer_fold_assignments_sha256": config["fold_assignments_sha256"],
                "hard_negative_unit": "recording", "hard_negative_fraction": .20,
                "hard_negative_weight_multiplier": 2.0, "ordinary_weight_multiplier": 1.0,
                "logistic_C_grid": list(C_GRID), "master_seed": 42,
                "single_change": "multiply existing Stage-1 fit segment weights by 2.0 for selected hard-negative recordings; ordinary by 1.0",
                "mining": "5 stratified inner participant folds inside each outer-training fold; Stage-1 inner fit/early-stop split only from inner-training participants; record score=mean segment probability; rank fit-role Absent recordings only; top ceil(20%); score ties by recording ID",
                "mining_seed": "42 + outer_fold for inner assignment; 42 + 10*outer_fold + inner_fold for inner early-stop split",
                "unchanged": "H016/H020 Stage-1 architecture, preprocessing, augmentation, class weighting policy, max epochs/patience, exact H015 outer folds, frozen encoder, uniform participant pooling, H020 scaler/L2 balanced logistic/C-grid/selection/threshold",
                "outer_eval": "excluded from inner mining and outer Stage-1 fit/early-stop; evaluated once",
                "encoder_initialization": "from_scratch; H014/H016 weights not reused for new outer encoder",
                "sample_weight_policy": "existing participant-balanced per-segment sample weights multiplied by recording hard-negative factor 2.0 or 1.0; internal early-stop remains unchanged",
                "success": {"minimum": "sensitivity>=.90 FP<160 F1>.53", "strong": "sensitivity>=.90 FP<=150", "very_strong": "sensitivity>=.90 FP<=120", "breakthrough": "sensitivity>=.90 FP<=80"},
                "external_validation_eligibility": {"sensitivity": .90, "specificity": .85, "precision": .65, "f1": .75, "roc_auc": .92, "pr_auc": .85},
                "validation_boundary": "never open external validation in H021", "sealed_test_boundary": "never open sealed holdout",
                "precheck_sha256": sha256(H020 / "representation_precheck/summary.json"),
                "config_sha256": hashlib.sha256((json.dumps(config, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()).hexdigest(),
                "source_sha256": {f: sha256(ROOT / f) for f in SOURCE},
                "environment": {"python": sys.executable, "tensorflow": tf.__version__, "gpu": gpu},
                "created_at": datetime.now(timezone.utc).isoformat()}
    A.mkdir(parents=True); R.mkdir(parents=True)
    write(A / "config.json", config)
    write(A / "protocol.json", protocol)
    (A / "protocol_sha256.txt").write_text(sha256(A / "protocol.json") + "\n")
    state("queued", protocol_sha256=sha256(A / "protocol.json"))
    print("H021 protocol SHA256", sha256(A / "protocol.json"), "GPU", gpu, flush=True)


def verify_lock(frame: pd.DataFrame) -> dict:
    p = read(A / "protocol.json"); c = read(A / "config.json")
    if sha256(A / "protocol.json") != (A / "protocol_sha256.txt").read_text().strip():
        raise ValueError("H021 protocol hash changed")
    if sha256(A / "config.json") != p["config_sha256"]:
        raise ValueError("H021 config hash changed")
    if any(sha256(ROOT / path) != digest for path, digest in p["source_sha256"].items()):
        raise ValueError("H021 source changed after protocol lock")
    if sha256(H015 / "fold_assignments.csv") != c["fold_assignments_sha256"] or sha256(H015 / "train_bag_inventory.csv") != c["train_inventory_sha256"]:
        raise ValueError("H021 fold/inventory changed")
    if hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest() != c["train_segments_sha256"]:
        raise ValueError("H021 TRAIN segments changed")
    return c


class EpochNotice(tf.keras.callbacks.Callback):
    def __init__(self, description: str):
        super().__init__(); self.description = description

    def on_epoch_begin(self, epoch: int, logs=None) -> None:
        print(f"{self.description}: Epoch {epoch+1}/50 started on /GPU:0", flush=True)
        state("running", phase=self.description, current_epoch=epoch+1)


def fit_stage1(fit: pd.DataFrame, early: pd.DataFrame, folder: Path, seed: int,
               description: str, multipliers: dict[str, float] | None = None):
    """H016 Stage-1 model/normalization/callback policy with optional H021 factor."""
    if (folder / "completed.json").exists():
        meta = read(folder / "completed.json")
        if sha256(folder / "best_model.keras") != meta["model_sha256"]:
            raise ValueError("Completed Stage-1 checkpoint changed")
        return tf.keras.models.load_model(folder / "best_model.keras"), read(folder / "normalization_config.json"), meta
    folder.mkdir(parents=True, exist_ok=True)
    config_file = folder / "normalization_config.json"
    if config_file.exists():
        config = read(config_file)
    else:
        config = read(H014 / "config.json")
        config.update(seed=seed, experiment_name=NAME)
        for key in ("spectrogram_frequency_mean", "spectrogram_frequency_std", "spectrogram_statistics_training_frames"):
            config.pop(key, None)
        mean, std, frames = _estimate_frequency_statistics(fit, ROOT, config)
        config.update(spectrogram_frequency_mean=mean, spectrogram_frequency_std=std,
                      spectrogram_statistics_training_frames=frames)
        write(config_file, config)
    tf.keras.utils.set_random_seed(seed)
    model = build_cnn_model((40, 313, 1), config, jit_compile=False)
    previous = reconcile_history(folder)
    write(folder / "status.json", {"status": "running", "phase": description})
    best_epoch, _, wait = best_record(previous)
    if len(previous) < 50 and wait < 8:
        print(f"{description}; fit segments={len(fit)} early segments={len(early)}; GPU /GPU:0", flush=True)
        model.fit(_dataset(fit, ROOT, config, True, True, multipliers),
                  validation_data=_dataset(early, ROOT, config, False, True),
                  epochs=50, callbacks=training_callbacks(tf, folder, 8, previous)+[EpochNotice(description)],
                  shuffle=False, verbose=2)
    history = reconcile_history(folder)
    best_epoch, best_loss, _ = sync_best_model(folder, history)
    if best_epoch is None:
        raise RuntimeError("Stage-1 had no completed epoch")
    model = tf.keras.models.load_model(folder / "best_model.keras")
    encoder = tf.keras.Model(model.input, model.layers[-2].output)
    meta = {"best_epoch": best_epoch, "best_internal_loss": best_loss,
            "model_sha256": sha256(folder / "best_model.keras"),
            "encoder_sha256": encoder_digest(encoder),
            "normalization_sha256": sha256(config_file),
            "fit_participants": int(fit.subject_group.nunique()), "early_participants": int(early.subject_group.nunique()),
            "fit_segments": len(fit), "early_segments": len(early),
            "hard_negative_multiplier_count": sum(v == 2.0 for v in (multipliers or {}).values())}
    write(folder / "completed.json", meta)
    history_plot(folder, description, best_epoch)
    write(folder / "status.json", {"status": "completed", **meta})
    return model, config, meta


def stage1_recording_scores(model, config: dict, held: pd.DataFrame, inner_fold: int) -> pd.DataFrame:
    scores = np.asarray(model.predict(_dataset(held, ROOT, config, False, False), verbose=0)).ravel()
    if len(scores) != len(held) or not np.isfinite(scores).all():
        raise ValueError("Invalid inner held Stage-1 segment scores")
    rows = held[["subject_group", "recording_id", "auscultation_location", "label"]].copy()
    rows["score"] = scores
    result = rows.groupby("recording_id", sort=True).agg(
        participant_id=("subject_group", "first"), site=("auscultation_location", "first"),
        true_label=("label", "first"), cross_fitted_score=("score", "mean"),
        segment_count=("score", "size")).reset_index()
    result["participant_id"] = result.participant_id.astype(str)
    result["inner_fold"] = inner_fold
    return result


def mine_fold(frame: pd.DataFrame, assignment: pd.DataFrame, audit: pd.DataFrame, fold: int) -> pd.DataFrame:
    inventory_file = A / "hard_negative_inventory" / f"fold_{fold}.csv"
    if inventory_file.exists():
        return pd.read_csv(inventory_file, dtype={"participant_id": str, "recording_id": str})
    parts = partitions(frame, assignment, audit, fold)
    outer_train = pd.concat([parts["fit"], parts["early_stop"]], ignore_index=True)
    outer_supervised = supervised(outer_train, audit)
    outer_eval_ids = set(parts["outer_eval"].subject_group.astype(str))
    inner = inner_assignments(outer_train, outer_eval_ids, fold)
    inner_path = R / "folds" / f"fold-{fold}" / "inner_assignments.csv"
    inner_path.parent.mkdir(parents=True, exist_ok=True)
    if inner_path.exists():
        if not pd.read_csv(inner_path, dtype={"participant_id": str}).equals(inner):
            raise ValueError("Inner fold assignments changed on resume")
    else:
        inner.to_csv(inner_path, index=False)
    tables = []
    for inner_fold in range(1, 6):
        held_ids = set(inner.loc[inner.inner_fold == inner_fold, "participant_id"])
        fit_ids, early_ids = inner_fit_early(outer_train, held_ids, fold, inner_fold)
        fit = outer_supervised.loc[outer_supervised.subject_group.astype(str).isin(fit_ids)].copy()
        early = outer_supervised.loc[outer_supervised.subject_group.astype(str).isin(early_ids)].copy()
        held = outer_supervised.loc[outer_supervised.subject_group.astype(str).isin(held_ids)].copy()
        if not held_ids.isdisjoint(outer_eval_ids) or set(fit.subject_group) & held_ids or set(early.subject_group) & held_ids:
            raise ValueError("Inner held participants leaked into acoustic fit")
        folder = R / "folds" / f"fold-{fold}" / "mining" / f"inner-{inner_fold}"
        score_file = folder / "recording_scores.csv"
        if score_file.exists():
            score = pd.read_csv(score_file, dtype={"participant_id": str, "recording_id": str})
        else:
            model, config, _ = fit_stage1(fit, early, folder, 42+fold*10+inner_fold,
                f"H021 mining outer={fold} inner={inner_fold}")
            score = stage1_recording_scores(model, config, held, inner_fold)
            score.to_csv(score_file, index=False)
            del model
            tf.keras.backend.clear_session()
        if set(score.participant_id) != held_ids or set(score.participant_id) & outer_eval_ids:
            raise ValueError("Cross-fitted recording score membership invalid")
        tables.append(score)
    scores = pd.concat(tables, ignore_index=True)
    if scores.recording_id.duplicated().any() or set(scores.recording_id) != set(outer_supervised.recording_id):
        raise ValueError("Inner cross-fitting did not cover each supervised outer-training recording once")
    eligible = set(parts["fit_supervised"].loc[parts["fit_supervised"].label == "Absent", "recording_id"])
    inventory = select_hard_negatives(scores, eligible)
    if inventory.hard_negative.sum() != math.ceil(.2 * len(eligible)):
        raise ValueError("Top-20% mining count incorrect")
    inventory_file.parent.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(inventory_file, index=False)
    print(f"H021 outer fold {fold}: hard negatives {int(inventory.hard_negative.sum())}/{len(eligible)} fit Absent recordings", flush=True)
    return inventory


def embedding_table(model, config: dict, frame: pd.DataFrame, fold: int) -> pd.DataFrame:
    encoder = tf.keras.Model(model.input, model.layers[-2].output)
    loader = BagTensorLoader(ROOT, config)
    result = []
    for bag in build_bags(frame):
        x = loader.tensors(bag, training=False)
        segments = np.asarray(encoder(x[0], training=False).numpy(), dtype=np.float32)
        if segments.shape != (bag.segment_count, 64) or not np.isfinite(segments).all():
            raise ValueError("Nonfinite or wrong acoustic embedding shape")
        recording = np.stack([segments[bag.segment_recording_index == i].mean(axis=0)
                              for i in range(bag.recording_count)])
        pooled = recording.mean(axis=0)
        result.append({"participant_id": bag.participant_id, "fold": fold,
                       "label": "Present" if bag.label else "Absent",
                       "recording_count": bag.recording_count,
                       **dict(zip(FEATURES, map(float, pooled), strict=True))})
    return pd.DataFrame(result)


def fold_result(frame, assignments, audit, fold):
    folder = R / "folds" / f"fold-{fold}"
    prediction_file = folder / "outer_predictions.csv"
    if prediction_file.exists():
        return pd.read_csv(prediction_file, dtype={"participant_id": str})
    inventory = mine_fold(frame, assignments, audit, fold)
    parts = partitions(frame, assignments, audit, fold)
    fit_ids = set(parts["fit_supervised"].recording_id)
    multipliers = dict(zip(inventory.recording_id.astype(str), inventory.sample_weight.astype(float), strict=True))
    multiplier_fit = {rid: multipliers[rid] for rid in fit_ids}
    model, config, meta = fit_stage1(parts["fit_supervised"], parts["early_supervised"],
        folder / "stage1", 42+fold, f"H021 outer fold={fold}", multiplier_fit)
    encoder = tf.keras.Model(model.input, model.layers[-2].output)
    if encoder_digest(encoder) != meta["encoder_sha256"]:
        raise ValueError("Outer fold acoustic encoder changed")
    outer_train = pd.concat([parts["fit"], parts["early_stop"]], ignore_index=True)
    train = embedding_table(model, config, outer_train, fold)
    held = embedding_table(model, config, parts["outer_eval"], fold)
    train.to_csv(folder / "train_embeddings.csv", index=False)
    held.to_csv(folder / "outer_embeddings.csv", index=False)
    selected, hp = choose_c(train, 42+fold)
    hp["outer_fold"] = fold; hp["selected"] = hp.C.eq(selected)
    hp.to_csv(folder / "inner_logistic_selection.csv", index=False)
    classifier = make_classifier(selected, 42+fold)
    classifier.fit(train.loc[:, FEATURES].to_numpy(float), train.label.eq("Present").to_numpy(int))
    scores = classifier.predict_proba(held.loc[:, FEATURES].to_numpy(float))[:, 1]
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite H021 outer-fold probabilities")
    scaler, logistic = classifier.steps[0][1], classifier.steps[1][1]
    np.savez(folder / "scaler_logistic.npz", scaler_mean=scaler.mean_, scaler_scale=scaler.scale_,
             scaler_var=scaler.var_, coef=logistic.coef_, intercept=logistic.intercept_, classes=logistic.classes_, C=selected)
    pred = held[["participant_id", "fold", "label"]].copy(); pred["probability"] = scores
    pred.to_csv(prediction_file, index=False)
    write(folder / "completed.json", {"fold": fold, "C": selected,
         "encoder_sha256": meta["encoder_sha256"],
         "encoder_model_sha256": meta["model_sha256"],
         "normalization_sha256": meta["normalization_sha256"],
         "hard_negative_count": int(inventory.hard_negative.sum()),
         "hard_negative_inventory_sha256": sha256(A / "hard_negative_inventory" / f"fold_{fold}.csv"),
         "outer_predictions_sha256": sha256(prediction_file)})
    print(f"H021 outer fold {fold}/5 complete; C={selected}; held participants={len(pred)}", flush=True)
    del model
    tf.keras.backend.clear_session()
    return pred


def plot_oof(pred: pd.DataFrame) -> None:
    y = pred.label.eq("Present").to_numpy(int); p = pred.probability.to_numpy(float)
    folder = A / "plots"; folder.mkdir(exist_ok=True)
    for kind in ("roc", "pr"):
        fig, ax = plt.subplots(figsize=(7, 5))
        if kind == "roc":
            x, z, _ = roc_curve(y, p); ax.plot(x, z, label=f"ROC-AUC {roc_auc_score(y,p):.3f}")
            ax.plot([0,1],[0,1],"--",color="gray")
            ax.set(xlabel="False positive rate",ylabel="True positive rate",title="H021 TRAIN OOF ROC")
        else:
            z, x, _ = precision_recall_curve(y, p); ax.plot(x, z, label=f"PR-AUC {average_precision_score(y,p):.3f}")
            ax.axhline(y.mean(),ls="--",color="gray")
            ax.set(xlabel="Recall",ylabel="Precision",title="H021 TRAIN OOF precision-recall")
        ax.legend(); fig.tight_layout(); fig.savefig(folder / f"{kind}_curve.png",dpi=180); plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,5))
    for label in ("Absent","Present"):
        ax.hist(pred.loc[pred.label==label,"probability"],bins=25,alpha=.55,label=label)
    ax.set(xlabel="OOF probability",ylabel="Participants",title="H021 TRAIN OOF scores")
    ax.legend(); fig.tight_layout(); fig.savefig(folder/"score_distribution.png",dpi=180); plt.close(fig)


def finalize(predictions: list[pd.DataFrame], assignments: pd.DataFrame, inventory: pd.DataFrame) -> None:
    pred = pd.concat(predictions, ignore_index=True).sort_values(["fold", "participant_id"])
    verify_train_oof(pred, assignments, inventory)
    trade = threshold_tradeoff(pred)
    chosen = best_at_sensitivity(trade, .90)
    y = pred.label.eq("Present").to_numpy(int)
    metrics = {"experiment": NAME, "population": "568 TRAIN outer-fold OOF participants", **chosen,
               "roc_auc": float(roc_auc_score(y, pred.probability)),
               "pr_auc": float(average_precision_score(y, pred.probability)),
               "confusion_matrix": [[chosen["tn"], chosen["fp"]], [chosen["fn"], chosen["tp"]]],
               "external_validation_opened": False, "sealed_test_opened": False,
               "protocol_sha256": sha256(A / "protocol.json")}
    gate = read(A / "protocol.json")["external_validation_eligibility"]
    metrics["eligible_for_external_validation"] = all(metrics[k] >= v for k,v in gate.items())
    metrics["minimum_meaningful"] = chosen["sensitivity"] >= .90 and chosen["fp"] < 160 and chosen["f1"] > .53
    metrics["strong"] = chosen["sensitivity"] >= .90 and chosen["fp"] <= 150
    metrics["very_strong"] = chosen["sensitivity"] >= .90 and chosen["fp"] <= 120
    metrics["breakthrough"] = chosen["sensitivity"] >= .90 and chosen["fp"] <= 80
    pred.to_csv(A / "predictions_oof.csv", index=False)
    trade.to_csv(A / "threshold_tradeoff.csv", index=False)
    fold_rows, hp_rows = [], []
    for fold in range(1,6):
        folder = R / "folds" / f"fold-{fold}"
        part = pred.loc[pred.fold == fold]; labels = part.label.eq("Present").to_numpy(int)
        fold_rows.append({"fold": fold, "participants": len(part),
            "roc_auc": float(roc_auc_score(labels,part.probability)),
            "pr_auc": float(average_precision_score(labels,part.probability)),
            **read(folder / "completed.json")})
        hp_rows.append(pd.read_csv(folder / "inner_logistic_selection.csv"))
    pd.DataFrame(fold_rows).to_csv(A / "fold_metrics.csv", index=False)
    pd.concat(hp_rows).to_csv(A / "fold_hyperparameters.csv", index=False)
    baseline = pd.read_csv(H020 / "comparison_h016_h020.csv")
    row = {column: metrics[column] for column in baseline.columns if column in metrics}
    row.update(experiment="H021", recall_sensitivity=metrics["sensitivity"])
    pd.concat([baseline,pd.DataFrame([row])],ignore_index=True).to_csv(A/"comparison_h016_h021.csv",index=False)
    plot_oof(pred)
    write(A / "metrics.json", metrics)
    reference = read(H020 / "metrics.json")
    delta = {k: metrics[k]-reference[k] for k in ("fp","fn","sensitivity","specificity","precision","f1","roc_auc","pr_auc")}
    summary = {"metrics": metrics, "h020_to_h021_delta": delta,
               "decision": "strong" if metrics["strong"] else "modest" if metrics["minimum_meaningful"] else "failed",
               "external_validation_opened": False, "sealed_test_opened": False,
               "next": "Stop; no H022 automatically"}
    write(A / "summary.json", summary)
    (A / "summary.md").write_text("# H021 TRAIN-only result\n\n"+json.dumps(summary,indent=2)+"\n")
    state("completed", metrics_path=str((A/"metrics.json").relative_to(ROOT)),
          oof_fp=chosen["fp"], oof_fn=chosen["fn"])
    print(json.dumps(summary,indent=2),flush=True)


def run() -> None:
    gpu_check()
    if not A.exists() or not R.exists():
        raise RuntimeError("Prepare and lock H021 protocol before run")
    lockfile = R / ".worker.lock"
    with lockfile.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("H021 worker already running") from exc
        if read(R / "status.json")["status"] == "completed":
            print("H021 already completed; skip",flush=True); return
        frame, assignments, audit, inventory = preflight()
        verify_lock(frame)
        state("running", phase="preflight", protocol_sha256=sha256(A / "protocol.json"))
        predictions = []
        for fold in range(1, 6):
            predictions.append(fold_result(frame, assignments, audit, fold))
        finalize(predictions, assignments, inventory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["smoke", "prepare", "run"])
    action = parser.parse_args().action
    {"smoke": smoke, "prepare": prepare, "run": run}[action]()

