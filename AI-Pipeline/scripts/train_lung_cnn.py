"""Lung preflight by default; fitting requires explicit user-authorized invocation."""
import argparse
import json
import os
import shutil
from pathlib import Path
import _bootstrap  # noqa: F401
from auriscore.lung_training import preflight, train, train_final

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--audit", type=Path, default=Path("data/processed/lung/audit.json"))
    p.add_argument("--output", type=Path, default=Path("results/EXP-L001-temporal-cnn"))
    p.add_argument("--folds", type=int, default=0)
    p.add_argument("--final-selection", type=Path, help="Frozen development selection for all-TRAIN final fitting")
    p.add_argument("--authorized-training", action="store_true", help="Use only after the user's explicit go-ahead")
    a = p.parse_args()
    if a.authorized_training:
        if a.final_selection:
            train_final(a.cache, a.audit, a.final_selection, a.output, authorized=True)
        else:
            train(a.cache, a.audit, a.output, authorized=True, folds=a.folds)
    else:
        config, index = preflight(a.cache, a.audit)
        print(json.dumps({"status": "preflight_only", "windows": len(index), "classes": config["classes"],
            "training_started": False, "cpu_count": os.cpu_count(), "free_bytes": shutil.disk_usage(a.cache).free}))
