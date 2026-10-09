"""H022 worker. Launch only through start_h022.sh after its locked preflight."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, roc_auc_score

import _bootstrap  # noqa: F401
from auriscore.cnn import _estimate_frequency_statistics, build_cnn_model
from auriscore.contrastive_acoustic import ContrastiveAcousticTrainer, stage1_dataset
from auriscore.experiment_runtime import best_record, reconcile_history, sync_best_model, training_callbacks
from auriscore.linear_head import FEATURES, choose_c, make_classifier
from auriscore.oof_audit import best_at_sensitivity, threshold_tradeoff, verify_train_oof
from auriscore.pretrained_mil import encoder_digest
from h022_preflight import H021, H022, H021_RESULTS, NAME, ROOT, audit_mining, digest, read_json, verify_lock
from train_h015_mil import gpu_check
from train_h016_mil import load_training, partitions
from train_h021_acoustic import embedding_table

RESULTS = ROOT / "results" / NAME
H014 = ROOT / "results/EXP-H014-cnn-per-frequency-augmentation-declared-positive-only"
H015 = ROOT / "analysis/EXP-H015-heart-site-aware-mil"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


class EpochNotice(tf.keras.callbacks.Callback):
    def __init__(self, fold: int):
        super().__init__()
        self.fold = fold

    def on_epoch_begin(self, epoch, logs=None):
        print(f"H022 outer fold={self.fold}: Epoch {epoch+1}/50 started on /GPU:0", flush=True)
        write_json(RESULTS / "status.json", {"status": "running", "fold": self.fold,
            "epoch": epoch + 1, "protocol_sha256": digest(H022 / "protocol.json"),
            "external_validation_opened": False, "sealed_test_opened": False})


def train_stage1(parts: dict, fold: int, multipliers: dict[str, float], hard_ids: set[str]):
    folder = RESULTS / "folds" / f"fold-{fold}" / "stage1"
    completed = folder / "completed.json"
    if completed.exists():
        metadata = read_json(completed)
        if digest(folder / "best_model.keras") != metadata["model_sha256"]:
            raise ValueError("H022 completed checkpoint hash mismatch")
        trainer = tf.keras.models.load_model(folder / "best_model.keras")
        return trainer.acoustic_model, read_json(folder / "normalization_config.json"), metadata
    folder.mkdir(parents=True, exist_ok=True)
    config_file = folder / "normalization_config.json"
    if config_file.exists():
        config = read_json(config_file)
    else:
        config = read_json(H014 / "config.json")
        config.update(seed=42 + fold, experiment_name=NAME)
        for key in ("spectrogram_frequency_mean", "spectrogram_frequency_std", "spectrogram_statistics_training_frames"):
            config.pop(key, None)
        mean, std, frames = _estimate_frequency_statistics(parts["fit_supervised"], ROOT, config)
        config.update(spectrogram_frequency_mean=mean, spectrogram_frequency_std=std,
                      spectrogram_statistics_training_frames=frames)
        write_json(config_file, config)
    tf.keras.utils.set_random_seed(42 + fold)
    acoustic = build_cnn_model((40, 313, 1), config, jit_compile=False)
    trainer = ContrastiveAcousticTrainer(acoustic, temperature=.10, representation_loss_weight=.10)
    trainer.compile(optimizer=tf.keras.optimizers.Adam(float(config.get("cnn_learning_rate", .001))), jit_compile=False)
    trainer(tf.zeros((1, 40, 313, 1), tf.float32))
    write_json(folder / "status.json", {"status": "running", "fold": fold})
    previous = reconcile_history(folder)
    _, _, wait = best_record(previous)
    if len(previous) < 50 and wait < 8:
        trainer.fit(stage1_dataset(parts["fit_supervised"], ROOT, config, True, multipliers, hard_ids),
                    validation_data=stage1_dataset(parts["early_supervised"], ROOT, config, False),
                    epochs=50, callbacks=training_callbacks(tf, folder, 8, previous) + [EpochNotice(fold)],
                    shuffle=False, verbose=2)
    history = reconcile_history(folder)
    best_epoch, best_loss, _ = sync_best_model(folder, history)
    if best_epoch is None:
        raise RuntimeError("H022 Stage-1 completed no epoch")
    trainer = tf.keras.models.load_model(folder / "best_model.keras")
    acoustic = trainer.acoustic_model
    encoder = tf.keras.Model(acoustic.input, acoustic.layers[-2].output)
    metadata = {"fold": fold, "best_epoch": best_epoch, "best_internal_loss": best_loss,
        "model_sha256": digest(folder / "best_model.keras"),
        "encoder_sha256": encoder_digest(encoder), "normalization_sha256": digest(config_file),
        "fit_participants": int(parts["fit_supervised"].subject_group.nunique()),
        "early_participants": int(parts["early_supervised"].subject_group.nunique()),
        "hard_negative_count": len(hard_ids)}
    write_json(completed, metadata)
    return acoustic, config, metadata


def run_fold(frame, assignments, audit, fold: int) -> pd.DataFrame:
    folder = RESULTS / "folds" / f"fold-{fold}"
    output = folder / "outer_predictions.csv"
    if output.exists():
        complete = read_json(folder / "completed.json")
        if digest(output) != complete["outer_predictions_sha256"]:
            raise ValueError("Completed H022 OOF output hash mismatch")
        return pd.read_csv(output, dtype={"participant_id": str})
    parts = partitions(frame, assignments, audit, fold)
    inventory_file = H021 / "hard_negative_inventory" / f"fold_{fold}.csv"
    inventory = pd.read_csv(inventory_file, dtype={"recording_id": str, "participant_id": str})
    expected = read_json(H022 / "protocol.json")["hard_negative_provenance"]["folds"][str(fold)]["inventory_sha256"]
    if digest(inventory_file) != expected:
        raise ValueError("H021 inventory changed after H022 protocol lock")
    fit_ids = set(parts["fit_supervised"].recording_id.astype(str))
    hard_ids = set(inventory.loc[inventory.hard_negative, "recording_id"].astype(str))
    if not hard_ids.issubset(fit_ids):
        raise ValueError("Hard negative entered from outside Stage-1 fit")
    multipliers = dict(zip(inventory.recording_id.astype(str), inventory.sample_weight.astype(float), strict=True))
    multipliers = {rid: multipliers[rid] for rid in fit_ids}
    acoustic, config, stage_meta = train_stage1(parts, fold, multipliers, hard_ids)
    train_frame = pd.concat([parts["fit"], parts["early_stop"]], ignore_index=True)
    train = embedding_table(acoustic, config, train_frame, fold)
    held = embedding_table(acoustic, config, parts["outer_eval"], fold)
    folder.mkdir(parents=True, exist_ok=True)
    train.to_csv(folder / "train_embeddings.csv", index=False)
    held.to_csv(folder / "outer_embeddings.csv", index=False)
    selected, choices = choose_c(train, 42 + fold)
    choices["outer_fold"] = fold
    choices["selected"] = choices.C.eq(selected)
    choices.to_csv(folder / "inner_logistic_selection.csv", index=False)
    classifier = make_classifier(selected, 42 + fold)
    classifier.fit(train.loc[:, FEATURES].to_numpy(float), train.label.eq("Present").to_numpy(int))
    scores = classifier.predict_proba(held.loc[:, FEATURES].to_numpy(float))[:, 1]
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite H022 participant probability")
    scaler, logistic = classifier.steps[0][1], classifier.steps[1][1]
    np.savez(folder / "scaler_logistic.npz", scaler_mean=scaler.mean_, scaler_scale=scaler.scale_,
             scaler_var=scaler.var_, coef=logistic.coef_, intercept=logistic.intercept_,
             classes=logistic.classes_, C=selected)
    prediction = held[["participant_id", "fold", "label"]].copy()
    prediction["probability"] = scores
    prediction.to_csv(output, index=False)
    write_json(folder / "completed.json", {"fold": fold, "C": selected,
        "encoder_sha256": stage_meta["encoder_sha256"],
        "hard_negative_inventory_sha256": digest(inventory_file),
        "outer_predictions_sha256": digest(output),
        "held_participants": len(prediction)})
    print(f"H022 outer fold {fold}/5 complete; held={len(prediction)}; C={selected}", flush=True)
    tf.keras.backend.clear_session()
    return prediction


def finalize(predictions: list[pd.DataFrame], assignments: pd.DataFrame) -> None:
    inventory = pd.read_csv(H015 / "train_bag_inventory.csv", dtype={"participant_id": str})
    pred = pd.concat(predictions, ignore_index=True).sort_values(["fold", "participant_id"])
    verify_train_oof(pred, assignments, inventory)
    trade = threshold_tradeoff(pred)
    chosen = best_at_sensitivity(trade, .90)
    labels = pred.label.eq("Present").to_numpy(int)
    metrics = {"experiment": NAME, "population": "568 TRAIN outer-fold OOF participants", **chosen,
        "roc_auc": float(roc_auc_score(labels, pred.probability)),
        "pr_auc": float(average_precision_score(labels, pred.probability)),
        "confusion_matrix": [[chosen["tn"], chosen["fp"]], [chosen["fn"], chosen["tp"]]],
        "protocol_sha256": digest(H022 / "protocol.json"),
        "external_validation_opened": False, "sealed_test_opened": False}
    gates = read_json(H022 / "protocol.json")["engineering_gates"]
    metrics["eligible_for_external_validation"] = all(metrics[key] >= value for key, value in gates.items())
    pred.to_csv(H022 / "predictions_oof.csv", index=False)
    trade.to_csv(H022 / "threshold_tradeoff.csv", index=False)
    write_json(H022 / "metrics.json", metrics)
    reference = read_json(H021 / "metrics.json")
    delta = {key: metrics[key] - reference[key] for key in
             ("fp", "fn", "sensitivity", "specificity", "precision", "f1", "roc_auc", "pr_auc")}
    write_json(H022 / "summary.json", {"metrics": metrics, "h021_to_h022_delta": delta,
        "external_validation_opened": False, "sealed_test_opened": False})
    write_json(RESULTS / "status.json", {"status": "completed", "metrics_path": str(H022 / "metrics.json"),
        "external_validation_opened": False, "sealed_test_opened": False})
    print(json.dumps({"metrics": metrics, "h021_to_h022_delta": delta}, indent=2), flush=True)


def run() -> None:
    verify_lock()
    gpu_check()
    if (H022 / "metrics.json").exists():
        raise RuntimeError("H022 OOF metrics already exist; refusing duplicate run")
    frame, assignments, audit = load_training()
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_json(RESULTS / "status.json", {"status": "running", "phase": "preflight",
        "protocol_sha256": digest(H022 / "protocol.json"),
        "external_validation_opened": False, "sealed_test_opened": False})
    predictions = [run_fold(frame, assignments, audit, fold) for fold in range(1, 6)]
    finalize(predictions, assignments)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run"])
    parser.parse_args()
    run()
