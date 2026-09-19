"""Run the one-time final evaluation of a sealed SVM or CNN holdout."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.config import load_config
from auriscore.holdout import evaluate_cnn_holdout, evaluate_svm_holdout
from auriscore.io import read_table


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=Path("configs/heart_baseline.yaml"))
    parser.add_argument("--model", type=Path, default=Path("artifacts/models/heart_svm.joblib"))
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        model_path = root / args.model
        config = load_config(root / args.config)
        if model_path.suffix == ".keras":
            result = evaluate_cnn_holdout(
                read_table(root / "data/processed/segments.csv"), config, root, model_path
            )
        else:
            result = evaluate_svm_holdout(
                read_table(root / "data/processed/features.csv"), config, root, model_path
            )
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot evaluate holdout: {exc}\n")
