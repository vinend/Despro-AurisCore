"""Lung preflight by default; fitting requires explicit user-authorized invocation."""
import argparse
import json
import os
import shutil
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_training import preflight, train, train_final
from auriscore.lung_training_policy import load_policy, model_dropout, model_dilation, optimizer_settings, selected_classes, model_bottleneck

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--audit", type=Path, default=Path("data/processed/lung/audit.json"))
    p.add_argument("--output", type=Path, default=Path("results/EXP-L001-temporal-cnn"))
    p.add_argument("--folds", type=int, default=0)
    p.add_argument("--progress-interval", type=float, default=30, help="Seconds between batch/window progress logs (default: 30)")
    p.add_argument("--training-policy", type=Path, help="Development LR/model policy; existing feature cache remains unchanged")
    p.add_argument("--final-selection", type=Path, help="Frozen development selection for all-TRAIN final fitting")
    p.add_argument("--authorized-training", action="store_true", help="Use only after the user's explicit go-ahead")
    p.add_argument("--require-gpu", action="store_true", help="Refuse CPU fallback for an explicitly GPU-only run")
    a = p.parse_args()
    if not 0 < a.progress_interval < float("inf"):
        p.error("--progress-interval must be finite and positive")
    if a.final_selection and a.training_policy:
        p.error("Final fitting must use frozen policy/epoch rates in --final-selection, not a validation-driven policy override")
    if a.authorized_training:
        if a.require_gpu:
            import tensorflow as tf
            devices = tf.config.list_physical_devices("GPU")
            if not devices:
                raise RuntimeError("GPU required; CPU fallback refused")
            for device in devices:
                tf.config.experimental.set_memory_growth(device, True)
        if a.final_selection:
            train_final(a.cache, a.audit, a.final_selection, a.output, authorized=True, progress_interval=a.progress_interval)
        else:
            train(a.cache, a.audit, a.output, authorized=True, folds=a.folds, training_policy=a.training_policy,
                  progress_interval=a.progress_interval)
    else:
        config, index = preflight(a.cache, a.audit)
        policy = load_policy(a.training_policy, config)
        print(json.dumps({"status": "preflight_only", "windows": len(index), "classes": selected_classes(policy, config),
            "training_policy": policy, "initial_learning_rate": optimizer_settings(policy, config)[0],
            "model_dropout": model_dropout(policy), "temporal_dilation": model_dilation(policy),
            "bottleneck_channels": model_bottleneck(policy),
            "training_started": False, "cpu_count": os.cpu_count(), "free_bytes": shutil.disk_usage(a.cache).free}))
