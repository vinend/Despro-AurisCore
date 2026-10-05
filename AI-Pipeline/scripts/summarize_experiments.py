"""Print completed validation results and regenerate the comparison figure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from auriscore.experiment_queue import is_completed
from auriscore.visualization import summarize_best, update_comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", help="Optional existing baseline EXP-H... directory")
    parser.add_argument("--best", help="Optional existing best EXP-H... directory")
    args = parser.parse_args()
    if bool(args.baseline) != bool(args.best):
        parser.error("--baseline and --best must be provided together")
    root = args.root.resolve()
    fields = (
        ("accuracy", "Accuracy"), ("precision", "Precision"),
        ("recall_sensitivity", "Recall"), ("specificity", "Specificity"),
        ("f1", "F1"), ("balanced_accuracy", "Balanced Acc"),
        ("roc_auc", "ROC-AUC"), ("pr_auc", "PR-AUC"),
    )
    try:
        directories = [directory for directory in sorted((root / "results").glob("EXP-H*"))
                       if directory.is_dir() and is_completed(directory)]
        print(f"{'Experiment':39} " + " ".join(f"{label:>12}" for _, label in fields) + f" {'Best Epoch':>10}")
        for directory in directories:
            data = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
            subject = data["validation"]["subject"]
            losses = data.get("training_history", {}).get("val_loss", [])
            epoch = min(range(len(losses)), key=lambda index: losses[index]) + 1 if losses else None
            values = " ".join(f"{subject[key]:12.4f}" if subject.get(key) is not None else f"{'-':>12}"
                              for key, _ in fields)
            print(f"{directory.name:39} {values} {epoch if epoch is not None else '-':>10}")
        if directories:
            update_comparison(root, directories[0])
        if args.baseline and args.best:
            print(f"Summary: {summarize_best(root, args.baseline, args.best)}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Cannot summarize experiments: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
