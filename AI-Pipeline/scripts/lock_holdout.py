"""Seal a genuinely new holdout before inspecting labels or training results."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.config import load_config
from auriscore.holdout import lock_holdout
from auriscore.io import read_table


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/heart_baseline.yaml"))
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        config = load_config(root / args.config)
        result = lock_holdout(read_table(root / "metadata/dataset_manifest.csv"), config, root)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot lock holdout: {exc}\n")
