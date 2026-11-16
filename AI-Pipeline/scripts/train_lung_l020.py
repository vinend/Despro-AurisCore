"""Run L020 or its L021 frame-loss source comparison on a CUDA GPU."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupShuffleSplit

from auriscore.acquisition_lung import digest
from auriscore.lung_clip_evaluation import nominal_clip_frames, reduce_clip_predictions
from auriscore.lung_evaluation import frame_metrics, select_thresholds
from auriscore.lung_interval_loss import interval_loss
from auriscore.lung_models import build_model
from auriscore.lung_objective import plan_supervision
from auriscore.lung_training import build_dataset, load_block, preflight, statistics

CLASSES = ["wheeze", "rhonchi", "crackle"]
ARMS = ["frame_hf", "interval_hf", "interval_hf_spr"]
SEED = 42
EPOCHS = 20
PATIENCE = 5
BATCH = 8


def physical_frames(rows, audit, config, frames):
    """Derive audio support independently of annotation coverage."""
    ends = pd.read_csv(audit.parent / "recordings.csv", usecols=["recording_id", "valid_end_s"])
    ends = ends.set_index("recording_id").valid_end_s
    end_samples = np.rint(ends.loc[rows.recording_id].to_numpy() * config["sample_rate"])
    starts = rows.file.str.removesuffix(".npz").str.rsplit("_", n=1).str[-1].astype(int)
    return end_samples[:, None] >= (
        starts.to_numpy()[:, None] + config["n_fft"] + np.arange(frames) * config["hop_length"]
    )


def development_arrays(cache, rows, indices):
    targets, masks = [], []
    for name in rows.file:
        _, truth, validity = load_block(cache / name)
        targets.append(truth[:, indices])
        masks.append(validity[:, indices])
    return np.asarray(targets), np.asarray(masks)


def clip_metrics(truth, scores, mask, thresholds):
    metrics = frame_metrics(truth, scores, mask, thresholds)
    for index, item in enumerate(metrics):
        item["accuracy"] = (item["tp"] + item["tn"]) / int(mask[..., index].sum())
        item["balanced_accuracy"] = (item["sensitivity"] + item["specificity"]) / 2
        item["scored_clips"] = int(mask[..., index].sum())
        item["excluded_slots"] = int(mask[..., index].size - mask[..., index].sum())
    return dict(zip(CLASSES, metrics))


def run(args):
    import tensorflow as tf

    def write(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    if not args.authorized_training or not tf.config.list_physical_devices("GPU"):
        raise RuntimeError("Explicit training authorization and CUDA GPU required")
    tf.config.experimental.enable_op_determinism()
    tf.config.experimental.enable_tensor_float_32_execution(False)
    hf_config, hf_rows = preflight(args.hf_audit.parent / args.hf_cache, args.hf_audit)
    hf_cache = args.hf_audit.parent / args.hf_cache
    spr_cache = args.spr_audit.parent / "cache"
    spr_config, spr_rows = preflight(spr_cache, args.spr_audit)
    columns = ["file", "group", "recording_id", "split", "source_sha256"]
    if hf_config != spr_config or not hf_rows[columns].reset_index(drop=True).equals(
        spr_rows.loc[~spr_rows.group.str.startswith("spr2022:"), columns].reset_index(drop=True)
    ):
        raise ValueError("SPRSound cache does not preserve the original HF population/configuration")
    additions = spr_rows[spr_rows.group.str.startswith("spr2022:")]
    if additions.empty or set(additions.split) != {"train"}:
        raise ValueError("Expected audited SPRSound TRAIN additions only")
    train = hf_rows[hf_rows.split == "train"]
    fit_idx, inner_idx = next(GroupShuffleSplit(n_splits=1, test_size=.20, random_state=SEED)
                              .split(train, groups=train.group))
    fit, inner = train.iloc[fit_idx], train.iloc[inner_idx]
    outer = hf_rows[hf_rows.split == "validation"]
    indices = [hf_config["classes"].index(name) for name in CLASSES]
    clip_frames = nominal_clip_frames(hf_config["sample_rate"], hf_config["hop_length"])
    if args.icbhi_train and not args.l020_control:
        raise ValueError("L023 requires the completed L020 frame HF control")
    arms = (["frame_hf_icbhi"] if args.icbhi_train else ["frame_hf_spr"]) if args.l020_control else ARMS
    control = None
    if args.l020_control:
        reference = args.l020_control
        protocol = json.loads((reference / "protocol.json").read_text())
        if (
            json.loads((reference / "status.json").read_text())["status"] != "completed"
            or protocol["experiment"] != "EXP-L020-interval-data"
            or protocol["input_hashes"]["hf_index"] != digest(hf_cache / "index.csv")
            or protocol["input_hashes"]["hf_audit"] != digest(args.hf_audit)
            or protocol["input_hashes"]["spr_index"] != digest(spr_cache / "index.csv")
            or protocol["input_hashes"]["spr_audit"] != digest(args.spr_audit)
            or protocol["fit_groups"] != sorted(fit.group.unique())
            or protocol["inner_groups"] != sorted(inner.group.unique())
            or protocol["outer_groups"] != sorted(outer.group.unique())
            or protocol["clip_frames"] != clip_frames
        ):
            raise ValueError("L021 requires the completed matched L020 control")
        control = json.loads((reference / "comparison.json").read_text())["frame_hf"]
    args.output.mkdir(parents=True, exist_ok=False)
    args._owns_output = True
    write(args.output / "protocol.json", {
        "experiment": ("EXP-L023-frame-icbhi" if args.icbhi_train else
                       "EXP-L021-frame-spr" if control else "EXP-L020-interval-data"),
        "arms": arms, "classes": CLASSES,
        "cycle_supervision": ({"source": "ICBHI official TRAIN, excluding test subjects",
                               "cycle_examples_per_step": 2, "weak_loss_multiplier": .8,
                               "pool": "max of complete physical frames", "rhonchi": "unknown",
                               "normalization": "HF fitting only"}
                              if args.icbhi_train else None),
        "control_sha256": digest(args.l020_control / "comparison.json") if control else None,
        "seed": SEED, "batch_size": BATCH, "epochs_max": EPOCHS, "patience": PATIENCE,
        "checkpoint": "max inner macro clip average precision",
        "thresholds": "per-class max F1 on inner only, grid .05..95 step .025, ties lowest",
        "clip_frames": clip_frames, "clip_decision": "maximum over physical frames, complete clips only",
        "grouping": "HF shifted date, SPR patient; HF patient independence unverified",
        "input_hashes": {k: digest(p) for k, p in {
            "hf_index": hf_cache / "index.csv", "hf_audit": args.hf_audit,
            "spr_index": spr_cache / "index.csv", "spr_audit": args.spr_audit,
            "runner": Path(__file__),
            "interval_loss": Path(__file__).resolve().parents[1] / "src/auriscore/lung_interval_loss.py",
            "clip_evaluation": Path(__file__).resolve().parents[1] / "src/auriscore/lung_clip_evaluation.py",
        }.items()},
        "config": hf_config, "fit_groups": sorted(fit.group.unique()),
        "inner_groups": sorted(inner.group.unique()), "outer_groups": sorted(outer.group.unique()),
        "spr_fit_windows": len(additions), "spr_fit_groups": additions.group.nunique(),
        "optimizer": {"type": "Adam", "lr": .001}, "dropout": .2, "dilation": 16,
        "official_test": "sealed", "deployment_eligible": False,
    })
    print(f"GPU={tf.config.list_physical_devices('GPU')} HF fit={len(fit)} inner={len(inner)} "
          f"outer={len(outer)} SPR train additions={len(additions)}", flush=True)
    write(args.output / "status.json", {"status": "running", "stage": "inner_preflight"})
    inner_y, inner_mask = development_arrays(hf_cache, inner, indices)
    physical = physical_frames(inner, args.hf_audit, hf_config, inner_y.shape[1])

    def clips(truth, scores, mask, valid):
        return reduce_clip_predictions(truth, scores, mask, valid, clip_frames=clip_frames)

    yy, _, mm = clips(inner_y, np.zeros_like(inner_y), inner_mask, physical)
    if any(len(np.unique(yy[..., i][mm[..., i]])) != 2 for i in range(len(CLASSES))):
        raise ValueError("Inner clips do not support both outcomes for each class")

    class InnerClipAP(tf.keras.callbacks.Callback):
        def __init__(self, data):
            super().__init__()
            self.data = data

        def on_epoch_end(self, epoch, logs=None):
            truth, scores, mask = clips(inner_y, self.model.predict(self.data, verbose=0), inner_mask, physical)
            values = [average_precision_score(truth[..., i][mask[..., i]], scores[..., i][mask[..., i]])
                      for i in range(len(CLASSES))]
            logs["inner_clip_ap"] = float(np.mean(values))
            for label, value in zip(CLASSES, values):
                logs[f"inner_ap_{label}"] = float(value)
            logs["optimizer_updates"] = int(self.model.optimizer.iterations.numpy())

    fitted = []
    if args.icbhi_train:
        from auriscore.lung_cycle_training import joint_loss, prepare_cycles
        write(args.output / "status.json", {"status": "running", "stage": "icbhi_audit"})
        weak_x, weak_targets, source_audit = prepare_cycles(
            args.icbhi_train, args.hf_audit.parent / "recordings.csv", hf_config
        )
        write(args.output / "icbhi_audit.json", source_audit)
        print(f"Audited ICBHI cycles: {len(weak_x)}", flush=True)
    for arm in arms:
        folder = args.output / arm
        folder.mkdir()
        write(args.output / "status.json", {"status": "running", "stage": "fit", "arm": arm})
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(SEED)
        mixed = arm.endswith("_spr")
        cache, rows = (spr_cache, pd.concat([fit, additions])) if mixed else (hf_cache, fit)
        print(f"{arm}: preparing {len(rows)} fitting windows", flush=True)
        mean, std, _ = statistics(cache, rows)
        rows, weights, report = plan_supervision(cache, rows, indices, {
            "positive_weighting": "window_mass", "empty_training_windows": "keep",
        })
        write(folder / "objective.json", report)
        np.savez(folder / "normalization.npz", mean=mean, std=std)
        shape = load_block(cache / rows.iloc[0].file)[0].shape
        def dataset(root, items, training=False):
            return build_dataset(root, items, mean, std, batch_size=BATCH, training=training,
                                 seed=SEED, class_indices=indices)

        model = build_model(shape, CLASSES, positive_weights=weights, temporal_dilation=16,
                            loss_numerics="stable_bce")
        training_data = dataset(cache, rows, training=True)
        if arm == "frame_hf_icbhi":
            model.compile(optimizer=model.optimizer, loss=joint_loss(weights))
            weak_data = tf.data.Dataset.from_tensor_slices(
                (np.clip((weak_x - mean) / std, -5, 5), weak_targets)
            ).shuffle(len(weak_x), seed=SEED).repeat().batch(2)

            def append_cycles(strong, weak):
                x, y = strong
                weak_features, weak_labels = weak
                return tf.concat([x, weak_features], 0), tf.concat([y, weak_labels], 0)

            training_data = tf.data.Dataset.zip((training_data, weak_data)).map(append_cycles).prefetch(1)
        if arm.startswith("interval_"):
            model.compile(optimizer=model.optimizer, loss=interval_loss(weights))
        inner_data = dataset(hf_cache, inner)
        history = model.fit(training_data, validation_data=inner_data,
                            epochs=EPOCHS, verbose=2, callbacks=[
            InnerClipAP(inner_data),
            tf.keras.callbacks.CSVLogger(str(folder / "history.csv")),
            tf.keras.callbacks.ModelCheckpoint(str(folder / "best.weights.h5"),
                                               monitor="inner_clip_ap", mode="max",
                                               save_best_only=True, save_weights_only=True),
            tf.keras.callbacks.EarlyStopping(monitor="inner_clip_ap", mode="max",
                                             patience=PATIENCE, restore_best_weights=True),
        ])
        model.load_weights(folder / "best.weights.h5")
        model.save(folder / "model.keras")
        write(folder / "history.json", history.history)
        y, p, m = clips(inner_y, model.predict(inner_data, verbose=0), inner_mask, physical)
        thresholds = select_thresholds(y, p, m)
        write(folder / "inner.json", {"thresholds": thresholds, "metrics": clip_metrics(y, p, m, thresholds)})
        fitted.append((arm, shape, mean, std, thresholds))

    write(args.output / "status.json", {"status": "running", "stage": "locked_development_evaluation"})
    outer_y, outer_mask = development_arrays(hf_cache, outer, indices)
    outer_valid = physical_frames(outer, args.hf_audit, hf_config, outer_y.shape[1])
    write(args.output / "prediction_index.json", outer[["file", "group"]].to_dict("records"))
    results = {}
    for arm, shape, mean, std, thresholds in fitted:
        tf.keras.backend.clear_session()
        folder = args.output / arm
        model = tf.keras.models.load_model(folder / "model.keras", compile=False)
        data = build_dataset(hf_cache, outer, mean, std, batch_size=BATCH, training=False,
                             seed=SEED, class_indices=indices)
        frame_scores = model.predict(data, verbose=0)
        y, p, m = clips(outer_y, frame_scores, outer_mask, outer_valid)
        metrics = clip_metrics(y, p, m, thresholds)
        np.savez_compressed(folder / "outer_predictions.npz", truth=outer_y, scores=frame_scores,
                            mask=outer_mask, clip_truth=y, clip_scores=p, clip_mask=m)
        results[arm] = {"metrics": metrics, "thresholds": thresholds, **{
            f"macro_{key}": float(np.mean([item[key] for item in metrics.values()]))
            for key in ["f1", "accuracy", "balanced_accuracy", "pr_auc"]
        }}
    if control:
        candidate = results[arms[0]]
        wheeze, rhonchi, crackle = (candidate["metrics"][name] for name in CLASSES)
        baseline_crackle = control["metrics"]["crackle"]
        results["frame_hf_control"] = control
        results["targets_met"] = {
            "macro_f1": candidate["macro_f1"] >= control["macro_f1"],
            "macro_accuracy": candidate["macro_accuracy"] >= .70,
            "macro_balanced_accuracy": candidate["macro_balanced_accuracy"] >= .70,
            "wheeze": wheeze["f1"] >= .81 and wheeze["sensitivity"] >= .81 and wheeze["specificity"] >= .60,
            "rhonchi": rhonchi["f1"] >= .65 and rhonchi["precision"] >= .55 and rhonchi["sensitivity"] >= .75,
            "crackle": crackle["f1"] >= baseline_crackle["f1"]
            and crackle["sensitivity"] >= baseline_crackle["sensitivity"] and crackle["specificity"] >= .55,
        }
    write(args.output / "comparison.json", results)
    write(args.output / "status.json", {"status": "completed", "deployment_eligible": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-audit", type=Path, required=True)
    parser.add_argument("--hf-cache", type=Path, required=True)
    parser.add_argument("--spr-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--l020-control", type=Path, help="Run L021 against this completed L020 result directory")
    parser.add_argument("--icbhi-train", type=Path, help="Run L023 with a verified ICBHI TRAIN staging directory")
    parser.add_argument("--authorized-training", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        status = args.output / "status.json"
        if status.is_file() and (args.output / "protocol.json").is_file() and getattr(args, "_owns_output", False):
            status.write_text(json.dumps({"status": "failed", "error": str(error)}), encoding="utf-8")
        raise
